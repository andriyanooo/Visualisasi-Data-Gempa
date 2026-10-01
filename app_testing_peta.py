import json
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.cluster import KMeans
from sklearn.metrics import davies_bouldin_score, silhouette_score
from sklearn.preprocessing import StandardScaler

st.set_page_config(page_title="Dashboard Gempa Indonesia", page_icon="🌋", layout="wide")

# =====================================================================
# CONFIG
# =====================================================================
BASE_DIR = Path(__file__).resolve().parent
XLSX_PATH = BASE_DIR / "df_Revisi.xlsx"
PARQUET_PATH = BASE_DIR / "df_Revisi.parquet"          # cache otomatis (lebih cepat dari Excel)
GEOJSON_PATH = BASE_DIR / "indonesia_provinsi.geojson"  # OPSIONAL, untuk peta choropleth

BULAN_MAP = {1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 5: "Mei", 6: "Juni",
             7: "Juli", 8: "Agustus", 9: "September", 10: "Oktober", 11: "November", 12: "Desember"}

FITUR_KLASTER = ["Magnitude", "Depth (km)", "Azimuth Gap"]

# Palet KATEGORIKAL netral untuk klaster kejadian (bukan skala risiko).
PALET_KLASTER = ["#4C78A8", "#F58518", "#54A24B", "#B279A2", "#9D755D"]

# Palet BERURUT untuk tingkat aktivitas wilayah (kuning -> merah tua).
LABEL_TINGKAT = {
    2: ["Rendah", "Tinggi"],
    3: ["Rendah", "Sedang", "Tinggi"],
    4: ["Rendah", "Sedang", "Tinggi", "Sangat Tinggi"],
    5: ["Sangat Rendah", "Rendah", "Sedang", "Tinggi", "Sangat Tinggi"],
}
WARNA_TINGKAT = {"Sangat Rendah": "#ffffb2", "Rendah": "#fecc5c", "Sedang": "#fd8d3c",
                 "Tinggi": "#e31a1c", "Sangat Tinggi": "#800026"}


# =====================================================================
# LOAD DATA  (poin 7: Parquet cache supaya start-up cepat)
# =====================================================================
@st.cache_data(show_spinner="Memuat data...")
def load_data():
    df = None
    if PARQUET_PATH.exists() and PARQUET_PATH.stat().st_mtime >= XLSX_PATH.stat().st_mtime:
        try:
            df = pd.read_parquet(PARQUET_PATH)
        except Exception:
            df = None
    if df is None:
        df = pd.read_excel(XLSX_PATH)
        df["Date time"] = pd.to_datetime(df["Date time"], errors="coerce", utc=True).dt.tz_localize(None)
        try:
            df.to_parquet(PARQUET_PATH, index=False)  # butuh pyarrow; kalau gagal, abaikan
        except Exception:
            pass

    df["Tahun"] = df["Date time"].dt.year
    df["Bulan"] = df["Date time"].dt.month
    df["Nama Bulan"] = df["Bulan"].map(BULAN_MAP)
    # Provinsi asli hanya terisi bila episenter di darat; untuk laut pakai provinsi terdekat.
    df["Provinsi_Tampil"] = df["Provinsi"].fillna(df["Provinsi_Terdekat"])
    df["Kabupaten_Kota_Tampil"] = df["Kabupaten_Kota"].fillna(df["Kabupaten_Kota_Terdekat"])
    return df


df = load_data()


# =====================================================================
# KARAKTERISASI KLASTER KEJADIAN  (poin 3 & 4)
# Label dihitung dari data, tanpa ambang 180 derajat yang tidak ada di naskah.
# Warna netral: klaster teknis BUKAN tingkat bahaya.
# =====================================================================
def kategori_kedalaman(depth):
    if depth < 70:
        return "Dangkal"
    return "Menengah" if depth <= 300 else "Dalam"


_gap_global = df["Azimuth Gap"].mean()
_stat = (df.groupby("cluster_label")
         .agg(Depth_mean=("Depth (km)", "mean"), Gap_mean=("Azimuth Gap", "mean"))
         .reset_index().sort_values(["Depth_mean", "Gap_mean"]).reset_index(drop=True))
_stat["Karakter"] = (_stat["Depth_mean"].apply(kategori_kedalaman) + " · Gap "
                     + np.where(_stat["Gap_mean"] > _gap_global, "Lebar", "Sempit"))
_stat["Nama"] = "Klaster " + _stat["cluster_label"].astype(str) + " (" + _stat["Karakter"] + ")"

CLUSTER_NAME = dict(zip(_stat["cluster_label"], _stat["Nama"]))
CLUSTER_ORDER = _stat["Nama"].tolist()
CLUSTER_COLOR = {n: PALET_KLASTER[i % len(PALET_KLASTER)] for i, n in enumerate(CLUSTER_ORDER)}
df["Nama_Klaster"] = df["cluster_label"].map(CLUSTER_NAME)


@st.cache_data
def eta_kuadrat():
    """Porsi variasi tiap fitur yang dijelaskan oleh klaster (0-1)."""
    hasil = {}
    for f in FITUR_KLASTER:
        sst = ((df[f] - df[f].mean()) ** 2).sum()
        ssb = sum(len(g) * (g[f].mean() - df[f].mean()) ** 2 for _, g in df.groupby("cluster_label"))
        hasil[f] = ssb / sst
    return pd.DataFrame({"Fitur": list(hasil), "Eta2": list(hasil.values())})


# =====================================================================
# KLASTERISASI WILAYAH (Opsi A): provinsi sebagai objek
# =====================================================================
@st.cache_data(show_spinner="Menghitung klaster wilayah...")
def klaster_wilayah(_df, tahun_tuple, k, min_n, max_jarak):
    d = _df[_df["Tahun"].isin(tahun_tuple)]
    d = d[(d["Status_Wilayah"] == "Darat") | (d["Jarak_ke_Daratan_km"] <= max_jarak)].copy()
    d["E"] = 10 ** (1.5 * d["Magnitude"] + 4.8)  # energi relatif (Gutenberg-Richter)

    g = d.groupby("Provinsi_Tampil").agg(
        n=("Magnitude", "size"),
        n5=("Magnitude", lambda s: int((s >= 5).sum())),
        mag_max=("Magnitude", "max"),
        E=("E", "sum"),
        depth_med=("Depth (km)", "median"),
        lat=("Latitude", "median"),
        lon=("Longitude", "median"),
    )
    g = g[g["n"] >= min_n].copy()
    if len(g) < 8:
        return None, None, None

    g["logn"] = np.log10(g["n"])
    g["logn5"] = np.log10(g["n5"] + 1)
    g["logE"] = np.log10(g["E"])
    fitur = ["logn", "logn5", "logE"]
    X = StandardScaler().fit_transform(g[fitur])

    # Evaluasi beberapa k agar pemilihan k transparan
    evaluasi = []
    for kk in range(2, 6):
        lab = KMeans(kk, random_state=42, n_init=20).fit_predict(X)
        evaluasi.append({"k": kk, "Silhouette": silhouette_score(X, lab),
                         "Davies-Bouldin": davies_bouldin_score(X, lab)})

    km = KMeans(k, random_state=42, n_init=20).fit(X)
    g["klaster"] = km.labels_
    skor = pd.Series(km.cluster_centers_.mean(axis=1))  # skor gabungan: rata-rata z-score fitur
    urut = skor.sort_values().index.tolist()
    peta = {c: LABEL_TINGKAT[k][i] for i, c in enumerate(urut)}
    g["Tingkat"] = g["klaster"].map(peta)
    g["Skor"] = g["klaster"].map(skor)
    g = g.reset_index().rename(columns={"Provinsi_Tampil": "Provinsi"})
    return g, pd.DataFrame(evaluasi), LABEL_TINGKAT[k]


@st.cache_data
def load_geojson():
    if not GEOJSON_PATH.exists():
        return None, None
    gj = json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))
    props = gj["features"][0]["properties"]
    for cand in ["NAME_1", "Provinsi", "PROVINSI", "provinsi", "Propinsi", "WADMPR", "name", "NAME"]:
        if cand in props:
            return gj, cand
    return gj, None


def norm_nama(s):
    return str(s).lower().replace("dki ", "").replace("daerah istimewa ", "").strip()


# =====================================================================
# SIDEBAR
# =====================================================================
st.sidebar.title("🌋 Filter Dashboard")

tahun_all = sorted(df["Tahun"].dropna().unique())
tahun = st.sidebar.multiselect("Tahun", tahun_all, default=tahun_all)
provinsi_all = sorted(df["Provinsi_Tampil"].dropna().unique())
provinsi = st.sidebar.multiselect("Provinsi (asli / terdekat)", provinsi_all, default=provinsi_all)
status_all = sorted(df["Status_Wilayah"].dropna().unique())
status_wilayah = st.sidebar.multiselect("Status Wilayah Episenter", status_all, default=status_all)
klaster_terpilih = st.sidebar.multiselect("Klaster kejadian", CLUSTER_ORDER, default=CLUSTER_ORDER)

mag_range = st.sidebar.slider("Magnitudo", float(df["Magnitude"].min()), float(df["Magnitude"].max()),
                              (float(df["Magnitude"].min()), float(df["Magnitude"].max())))
depth_range = st.sidebar.slider("Kedalaman (km)", int(df["Depth (km)"].min()), int(df["Depth (km)"].max()),
                                (int(df["Depth (km)"].min()), int(df["Depth (km)"].max())))

with st.sidebar.expander("⚙️ Filter Lanjutan"):
    mag_type_all = sorted(df["Mag Type"].dropna().unique())
    mag_type = st.multiselect("Tipe Magnitudo", mag_type_all, default=mag_type_all)
    jarak_max = float(df["Jarak_ke_Daratan_km"].max())
    jarak_range = st.slider("Jarak ke Daratan (km, khusus episenter laut)", 0.0, jarak_max, (0.0, jarak_max))
    kecuali_10km = st.checkbox("Sembunyikan kedalaman tepat 10 km (kemungkinan nilai default)", value=False)

mask = (
    df["Tahun"].isin(tahun)
    & df["Provinsi_Tampil"].isin(provinsi)
    & df["Status_Wilayah"].isin(status_wilayah)
    & df["Nama_Klaster"].isin(klaster_terpilih)
    & df["Magnitude"].between(*mag_range)
    & df["Depth (km)"].between(*depth_range)
    & df["Mag Type"].isin(mag_type)
    & ((df["Status_Wilayah"] != "Laut") | df["Jarak_ke_Daratan_km"].between(*jarak_range))
)
if kecuali_10km:
    mask &= df["Depth (km)"] != 10
filtered = df[mask]

# =====================================================================
# HEADER & KPI
# =====================================================================
st.title("🌋 Dashboard Klasterisasi Gempa Bumi Indonesia")

n = len(filtered)
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total Gempa", f"{n:,}")
c2.metric("Magnitudo Maks", round(filtered["Magnitude"].max(), 2) if n else "-")
c3.metric("Magnitudo Rata-rata", round(filtered["Magnitude"].mean(), 2) if n else "-")
c4.metric("Kedalaman Median (km)", round(filtered["Depth (km)"].median(), 1) if n else "-")
c5.metric("Gempa M ≥ 5", f"{int((filtered['Magnitude'] >= 5).sum()):,}" if n else "-")
c6.metric("Episenter di Laut", f"{(filtered['Status_Wilayah'] == 'Laut').mean() * 100:.1f}%" if n else "-")

tabs = st.tabs(["🗺️ Peta Kejadian", "📍 Aktivitas Wilayah", "📊 Statistik", "🎯 Analisis Klaster",
                "🌊 Laut & Darat", "📋 Dataset", "📝 Catatan Data"])

# =====================================================================
# TAB 1: PETA KEJADIAN  (poin 2 & 3: sampel titik + mode kepadatan, warna netral)
# =====================================================================
with tabs[0]:
    st.subheader("Sebaran Kejadian Gempa")
    a, b, c = st.columns([1.2, 1, 1])
    mode = a.radio("Mode tampilan", ["Titik per klaster", "Kepadatan (density)"], horizontal=True)
    map_style = b.selectbox("Gaya peta", ["carto-positron", "open-street-map", "carto-darkmatter", "satellite-streets"])
    max_titik = c.slider("Maks. titik ditampilkan", 2000, 60000, 15000, step=1000,
                         help="Diambil acak agar peta tetap ringan.")

    if n == 0:
        st.info("Tidak ada data yang cocok dengan filter saat ini.")
    else:
        tmp = filtered.sample(max_titik, random_state=42) if n > max_titik else filtered
        center = {"lat": -2.5, "lon": 118}
        if mode == "Titik per klaster":
            fig = px.scatter_map(
                tmp, lat="Latitude", lon="Longitude", color="Nama_Klaster",
                category_orders={"Nama_Klaster": CLUSTER_ORDER}, color_discrete_map=CLUSTER_COLOR,
                hover_name="Wilayah_Detail",
                hover_data={"Provinsi_Tampil": True, "Status_Wilayah": True, "Magnitude": ":.1f",
                            "Depth (km)": True, "Tahun": True, "Latitude": False, "Longitude": False},
                opacity=0.55, zoom=3.6, center=center)
            fig.update_traces(marker=dict(size=5))
        else:
            fig = px.density_map(tmp, lat="Latitude", lon="Longitude", radius=8, zoom=3.6, center=center,
                                 color_continuous_scale="YlOrRd")
        fig.update_layout(map_style=map_style, margin={"r": 0, "t": 10, "l": 0, "b": 0}, height=600,
                          legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1))
        st.plotly_chart(fig, width="stretch")
        if n > max_titik:
            st.caption(f"Menampilkan sampel acak {max_titik:,} dari {n:,} kejadian.")
        st.caption("⚠️ Warna klaster bersifat **kategorikal netral**: klaster ini dibentuk oleh kedalaman dan "
                   "azimuth gap, sehingga **tidak menunjukkan tingkat bahaya**. Untuk tingkat aktivitas per "
                   "wilayah, lihat tab *Aktivitas Wilayah*.")

# =====================================================================
# TAB 2: AKTIVITAS WILAYAH (Opsi A)
# =====================================================================
with tabs[1]:
    st.subheader("Klasterisasi Wilayah (Provinsi) berdasarkan Aktivitas Kegempaan Historis")
    st.caption("Objek klaster = **provinsi**. Fitur: log jumlah kejadian, log jumlah gempa M ≥ 5, dan log total "
               "energi relatif. Tingkat (Rendah–Tinggi) diurutkan dari skor gabungan centroid. Ini indikator "
               "**aktivitas historis katalog BMKG**, bukan risiko: belum memuat sesar aktif, kerentanan bangunan, "
               "atau kepadatan penduduk.")
    a, b, c = st.columns(3)
    k_w = a.slider("Jumlah klaster (k)", 2, 5, 3)
    min_n = b.slider("Minimum kejadian per provinsi", 10, 200, 30, step=10)
    max_jarak = c.slider("Batas jarak episenter laut ke daratan (km)", 25, 900, 100, step=25,
                         help="Episenter laut yang lebih jauh dari batas ini tidak dihitung ke provinsi mana pun.")

    hasil, evaluasi, urutan = klaster_wilayah(df, tuple(tahun), k_w, min_n, float(max_jarak))
    if hasil is None:
        st.warning("Provinsi yang memenuhi syarat terlalu sedikit. Turunkan minimum kejadian atau perluas filter tahun.")
    else:
        gj, gj_key = load_geojson()
        warna = {t: WARNA_TINGKAT[t] for t in urutan}
        dipakai_choropleth = False
        if gj is not None and gj_key is not None:
            lookup = {norm_nama(f["properties"][gj_key]): f["properties"][gj_key] for f in gj["features"]}
            hasil["geo_key"] = hasil["Provinsi"].map(lambda s: lookup.get(norm_nama(s)))
            cocok = hasil["geo_key"].notna().mean()
            if cocok >= 0.7:
                dipakai_choropleth = True
            else:
                st.warning(f"Nama provinsi hanya cocok {cocok:.0%} dengan GeoJSON. Menampilkan peta gelembung.")

        if dipakai_choropleth:
            fig_w = px.choropleth_map(
                hasil.dropna(subset=["geo_key"]), geojson=gj, locations="geo_key",
                featureidkey=f"properties.{gj_key}", color="Tingkat", color_discrete_map=warna,
                category_orders={"Tingkat": urutan}, hover_name="Provinsi",
                hover_data={"n": True, "n5": True, "mag_max": ":.1f", "geo_key": False},
                zoom=3.6, center={"lat": -2.5, "lon": 118}, opacity=0.8)
        else:
            fig_w = px.scatter_map(
                hasil, lat="lat", lon="lon", size="n", size_max=40, color="Tingkat",
                color_discrete_map=warna, category_orders={"Tingkat": urutan}, hover_name="Provinsi",
                hover_data={"n": True, "n5": True, "mag_max": ":.1f", "lat": False, "lon": False},
                zoom=3.6, center={"lat": -2.5, "lon": 118}, opacity=0.8)
            if gj is None:
                st.info("Untuk peta area (choropleth), simpan GeoJSON batas provinsi sebagai "
                        "`indonesia_provinsi.geojson` di folder yang sama dengan file ini. "
                        "Sementara ditampilkan peta gelembung (titik = median lokasi kejadian provinsi).")
        fig_w.update_layout(map_style="carto-positron", height=560, margin={"r": 0, "t": 10, "l": 0, "b": 0})
        st.plotly_chart(fig_w, width="stretch")

        colA, colB = st.columns([1.3, 1])
        with colA:
            st.markdown("#### Daftar provinsi per tingkat")
            tampil = (hasil.sort_values(["Skor", "n"], ascending=False)
                      [["Provinsi", "Tingkat", "n", "n5", "mag_max", "depth_med"]]
                      .rename(columns={"n": "Jumlah kejadian", "n5": "Gempa M≥5", "mag_max": "Magnitudo maks",
                                       "depth_med": "Median kedalaman (km)"}))
            st.dataframe(tampil.round(2), width="stretch", height=380, hide_index=True)
        with colB:
            st.markdown("#### Evaluasi pemilihan k")
            st.dataframe(evaluasi.round(3), width="stretch", hide_index=True)
            st.caption(f"k dipilih = {k_w}. Bandingkan Silhouette (tinggi lebih baik) dan Davies-Bouldin "
                       f"(rendah lebih baik) sebelum memutuskan k. Jumlah provinsi dianalisis: {len(hasil)}.")
            profil = hasil.groupby("Tingkat")[["n", "n5", "mag_max"]].mean().reindex(urutan).round(1)
            profil["Jumlah provinsi"] = hasil.groupby("Tingkat").size().reindex(urutan)
            st.markdown("**Profil rata-rata tiap tingkat**")
            st.dataframe(profil, width="stretch")

        st.caption("⚠️ Provinsi dengan kejadian sedikit tetapi banyak M≥5 (mis. Kalimantan) umumnya mencerminkan "
                   "keterbatasan deteksi katalog untuk gempa kecil, bukan aktivitas tinggi. Validasi hasil ini "
                   "dengan Peta Sumber dan Bahaya Gempa Indonesia (PuSGeN) atau data dampak BNPB.")

# =====================================================================
# TAB 3: STATISTIK  (poin 6: catatan lonjakan 2025 + M>=5 sebagai pembanding)
# =====================================================================
with tabs[2]:
    if n == 0:
        st.info("Tidak ada data yang cocok dengan filter saat ini.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            ts = filtered.groupby("Tahun").size().reset_index(name="Jumlah")
            fig1 = px.line(ts, x="Tahun", y="Jumlah", markers=True, title="Jumlah semua kejadian per tahun")
            st.plotly_chart(fig1, width="stretch")
        with col2:
            t5 = filtered[filtered["Magnitude"] >= 5].groupby("Tahun").size().reset_index(name="Jumlah")
            fig1b = px.line(t5, x="Tahun", y="Jumlah", markers=True, title="Jumlah gempa M ≥ 5 per tahun")
            st.plotly_chart(fig1b, width="stretch")
        st.caption("⚠️ Lonjakan 2025 pada grafik kiri belum tentu peningkatan aktivitas: bisa berasal dari "
                   "bertambahnya stasiun/kemampuan deteksi gempa kecil. Grafik M ≥ 5 lebih tahan terhadap "
                   "bias deteksi, sehingga lebih layak dipakai untuk membaca tren.")

        col3, col4 = st.columns(2)
        with col3:
            bs = (filtered.groupby(["Bulan", "Nama Bulan"]).size().reset_index(name="Jumlah").sort_values("Bulan"))
            fig2 = px.bar(bs, x="Nama Bulan", y="Jumlah", title="Jumlah kejadian per bulan")
            fig2.update_xaxes(categoryorder="array", categoryarray=list(BULAN_MAP.values()))
            st.plotly_chart(fig2, width="stretch")
        with col4:
            heat = pd.pivot_table(filtered, index="Tahun", columns="Nama Bulan", values="Magnitude",
                                  aggfunc="count", fill_value=0)
            heat = heat.reindex(columns=[m for m in BULAN_MAP.values() if m in heat.columns])
            st.plotly_chart(px.imshow(heat, text_auto=True, aspect="auto", color_continuous_scale="OrRd",
                                      title="Heatmap kejadian: tahun × bulan"), width="stretch")

        col5, col6 = st.columns(2)
        with col5:
            tp = filtered["Provinsi_Tampil"].value_counts().head(20).reset_index()
            tp.columns = ["Provinsi", "Jumlah"]
            st.plotly_chart(px.bar(tp, x="Provinsi", y="Jumlah",
                                   title="20 provinsi dengan kejadian terbanyak (asli/terdekat)"),
                            width="stretch")
        with col6:
            mt = filtered["Mag Type"].value_counts().reset_index()
            mt.columns = ["Mag Type", "Jumlah"]
            st.plotly_chart(px.pie(mt, names="Mag Type", values="Jumlah", hole=0.4,
                                   title="Komposisi tipe magnitudo"), width="stretch")

# =====================================================================
# TAB 4: ANALISIS KLASTER  (poin 1 & 5: ukuran klaster, korelasi, boxplot, eta2)
# =====================================================================
with tabs[3]:
    st.subheader("Karakteristik Klaster Kejadian")
    st.caption("Klaster dibentuk K-Means dari **Magnitude**, **Depth (km)**, dan **Azimuth Gap** (k = 3, Min-Max). "
               "Azimuth gap mencerminkan geometri jaringan stasiun, bukan sifat fisik gempa.")

    if n == 0:
        st.info("Tidak ada data yang cocok dengan filter saat ini.")
    else:
        # Ukuran klaster
        ukuran = filtered["Nama_Klaster"].value_counts().reindex(CLUSTER_ORDER).dropna().reset_index()
        ukuran.columns = ["Klaster", "Jumlah"]
        ukuran["Persen"] = (ukuran["Jumlah"] / ukuran["Jumlah"].sum() * 100).round(1)
        colA, colB = st.columns(2)
        with colA:
            fu = px.bar(ukuran, x="Klaster", y="Jumlah", color="Klaster", text=ukuran["Persen"].map("{:.1f}%".format),
                        color_discrete_map=CLUSTER_COLOR, title="Jumlah anggota tiap klaster")
            fu.update_layout(showlegend=False, xaxis_title=None)
            fu.update_traces(textposition="outside")
            st.plotly_chart(fu, width="stretch")
        with colB:
            eta = eta_kuadrat()
            fe = px.bar(eta, x="Fitur", y="Eta2", text=eta["Eta2"].map("{:.2f}".format),
                        title="Seberapa kuat fitur membedakan klaster (η², 0–1)")
            fe.update_traces(textposition="outside")
            fe.update_yaxes(range=[0, 1])
            st.plotly_chart(fe, width="stretch")
            st.caption("η² dihitung pada seluruh data. Nilai Magnitude yang sangat kecil berarti klaster "
                       "hampir tidak dibedakan oleh kekuatan gempa.")

        # Ringkasan (median lebih tahan terhadap data miring)
        st.markdown("#### Ringkasan per klaster (rata-rata dan median)")
        ringkas = (filtered.groupby("Nama_Klaster")
                   .agg(Jumlah=("Magnitude", "size"),
                        Mag_rata=("Magnitude", "mean"), Mag_median=("Magnitude", "median"),
                        Depth_rata=("Depth (km)", "mean"), Depth_median=("Depth (km)", "median"),
                        Gap_rata=("Azimuth Gap", "mean"), Gap_median=("Azimuth Gap", "median"),
                        Persen_10km=("Depth (km)", lambda s: (s == 10).mean() * 100))
                   .reindex(CLUSTER_ORDER).dropna().round(2))
        st.dataframe(ringkas, width="stretch")

        # Boxplot (poin 5)
        st.markdown("#### Sebaran nilai per klaster (boxplot)")
        log_depth = st.checkbox("Skala log untuk kedalaman", value=True)
        samp = filtered.sample(min(n, 20000), random_state=1)
        cb = st.columns(3)
        for col, f, lg in zip(cb, FITUR_KLASTER, [False, log_depth, False]):
            with col:
                fb = px.box(samp, x="Nama_Klaster", y=f, color="Nama_Klaster", log_y=lg,
                            category_orders={"Nama_Klaster": CLUSTER_ORDER}, color_discrete_map=CLUSTER_COLOR,
                            title=f)
                fb.update_layout(showlegend=False, xaxis_title=None, xaxis_showticklabels=False)
                st.plotly_chart(fb, width="stretch")

        # Korelasi (poin 1)
        colC, colD = st.columns(2)
        with colC:
            corr = filtered[FITUR_KLASTER].corr().round(2)
            st.plotly_chart(px.imshow(corr, text_auto=True, zmin=-1, zmax=1, color_continuous_scale="RdBu_r",
                                      title="Korelasi antar fitur"), width="stretch")
        with colD:
            sc = filtered.sample(min(n, 8000), random_state=42)
            fs = px.scatter(sc, x="Depth (km)", y="Azimuth Gap", color="Nama_Klaster", opacity=0.5,
                            category_orders={"Nama_Klaster": CLUSTER_ORDER}, color_discrete_map=CLUSTER_COLOR,
                            title="Kedalaman vs Azimuth Gap")
            st.plotly_chart(fs, width="stretch")

        st_kl = (filtered.groupby(["Nama_Klaster", "Status_Wilayah"]).size().reset_index(name="Jumlah"))
        st_kl["Persen"] = st_kl["Jumlah"] / st_kl.groupby("Nama_Klaster")["Jumlah"].transform("sum") * 100
        st.plotly_chart(px.bar(st_kl, x="Nama_Klaster", y="Persen", color="Status_Wilayah", barmode="stack",
                               category_orders={"Nama_Klaster": CLUSTER_ORDER},
                               color_discrete_map={"Laut": "#3498DB", "Darat": "#8B5E3C"},
                               title="Komposisi laut vs darat per klaster (%)"), width="stretch")

# =====================================================================
# TAB 5: LAUT & DARAT
# =====================================================================
with tabs[4]:
    if n == 0:
        st.info("Tidak ada data yang cocok dengan filter saat ini.")
    else:
        colL, colR = st.columns(2)
        with colL:
            sc_ = filtered["Status_Wilayah"].value_counts().reset_index()
            sc_.columns = ["Status", "Jumlah"]
            st.plotly_chart(px.pie(sc_, names="Status", values="Jumlah", hole=0.4, color="Status",
                                   color_discrete_map={"Laut": "#3498DB", "Darat": "#8B5E3C"},
                                   title="Proporsi laut vs darat"), width="stretch")
        with colR:
            laut = filtered[filtered["Status_Wilayah"] == "Laut"]
            if len(laut):
                st.plotly_chart(px.histogram(laut, x="Jarak_ke_Daratan_km", nbins=40,
                                             title="Jarak episenter laut ke daratan terdekat (km)"),
                                width="stretch")
                st.caption(f"Rata-rata {laut['Jarak_ke_Daratan_km'].mean():.1f} km | median "
                           f"{laut['Jarak_ke_Daratan_km'].median():.1f} km | terjauh "
                           f"{laut['Jarak_ke_Daratan_km'].max():.1f} km. Atribusi provinsi untuk episenter "
                           "yang jauh dari pantai kurang bermakna.")
        colM, colN = st.columns(2)
        with colM:
            st.markdown("#### 10 kabupaten/kota teratas (darat)")
            t = filtered[filtered["Status_Wilayah"] == "Darat"]["Kabupaten_Kota_Tampil"].value_counts().head(10)
            st.dataframe(t.rename_axis("Kabupaten/Kota").reset_index(name="Jumlah"), width="stretch")
        with colN:
            st.markdown("#### 10 kabupaten/kota terdekat teratas (laut)")
            t = filtered[filtered["Status_Wilayah"] == "Laut"]["Kabupaten_Kota_Tampil"].value_counts().head(10)
            st.dataframe(t.rename_axis("Kabupaten/Kota Terdekat").reset_index(name="Jumlah"),
                         width="stretch")

# =====================================================================
# TAB 6: DATASET
# =====================================================================
with tabs[5]:
    st.subheader("Dataset")
    kata = st.text_input("🔎 Cari kata kunci", placeholder="Contoh: nama provinsi, klaster, dll.")
    semua_kolom = st.checkbox("Tampilkan semua kolom", value=False)
    ringkas_cols = ["Event ID", "Date time", "Tahun", "Latitude", "Longitude", "Magnitude", "Mag Type",
                    "Depth (km)", "Azimuth Gap", "Provinsi_Tampil", "Kabupaten_Kota_Tampil", "Status_Wilayah",
                    "Jarak_ke_Daratan_km", "cluster_label", "Nama_Klaster"]
    view = filtered.copy() if semua_kolom else filtered[ringkas_cols].copy()
    if kata:
        kw = kata.strip().lower()
        m = pd.Series(False, index=view.index)
        for col in view.columns:
            m |= view[col].astype(str).str.lower().str.contains(kw, na=False, regex=False)
        view = view[m]
    st.caption(f"Menampilkan {len(view):,} dari {len(filtered):,} data hasil filter.")
    st.dataframe(view.head(2000), width="stretch", height=450)
    if len(view) > 2000:
        st.caption("Tabel dibatasi 2.000 baris pertama agar responsif; file unduhan berisi seluruh hasil.")

    @st.cache_data(show_spinner=False)
    def _csv(_d, key):
        return _d.to_csv(index=False).encode("utf-8")

    @st.cache_data(show_spinner=False)
    def _xlsx(_d, key):
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            _d.to_excel(w, index=False)
        return buf.getvalue()

    key = f"{len(view)}_{int(view['Magnitude'].sum() * 1000) if len(view) else 0}_{kata}_{semua_kolom}"
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ Unduh CSV", _csv(view, key), "dataset_gempa.csv", "text/csv",
                       key=f"csv_{key}", width="stretch")
    d2.download_button("⬇️ Unduh Excel", _xlsx(view, key), "dataset_gempa.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key=f"xlsx_{key}", width="stretch")

# =====================================================================
# TAB 7: CATATAN DATA (transparansi keterbatasan)
# =====================================================================
with tabs[6]:
    st.subheader("Catatan Kualitas Data dan Keterbatasan")
    tot = len(df)
    p10 = (df["Depth (km)"] == 10).mean() * 100
    p25 = (df["Tahun"] == 2025).mean() * 100
    plaut = (df["Status_Wilayah"] == "Laut").mean() * 100
    pmag = df["Mag Type"].value_counts(normalize=True).head(2) * 100
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Kedalaman tepat 10 km", f"{p10:.1f}%")
    m2.metric("Porsi data tahun 2025", f"{p25:.1f}%")
    m3.metric("Episenter di laut", f"{plaut:.1f}%")
    m4.metric("Tipe magnitudo dominan", " / ".join(pmag.index))
    st.markdown(
        "- **Kedalaman 10 km** muncul sangat sering dan kemungkinan merupakan nilai default penentuan hiposenter, "
        "bukan hasil pengukuran. Gunakan opsi *Sembunyikan kedalaman tepat 10 km* di sidebar untuk melihat pengaruhnya.\n"
        "- **Tipe magnitudo campuran** (M, MLv, Mw, mb, dll.) belum diseragamkan.\n"
        "- **Aftershock belum di-declustering**, sehingga satu rangkaian gempa besar dapat menggelembungkan jumlah kejadian.\n"
        "- **Lonjakan 2025** dapat berasal dari peningkatan deteksi; gunakan grafik M ≥ 5 untuk membaca tren.\n"
        "- **Azimuth gap** adalah kualitas geometri stasiun, sehingga klaster kejadian tidak dapat dibaca sebagai tingkat bahaya.\n"
        "- **Episenter laut** diberi provinsi terdekat; jaraknya bisa sangat jauh dari pantai.\n"
        "- **Frekuensi kejadian bukan ukuran risiko.** Hasil dashboard belum menggantikan peta bahaya gempa resmi."
    )
    dh = px.histogram(df, x="Depth (km)", nbins=120, title="Distribusi kedalaman (perhatikan lonjakan di 10 km)")
    st.plotly_chart(dh, width="stretch")