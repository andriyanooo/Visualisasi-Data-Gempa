import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO
from pathlib import Path

st.set_page_config(
    page_title="Dashboard Gempa Indonesia",
    page_icon="🌋",
    layout="wide"
)

# =========================
# CONFIG
# =========================
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "df_final.xlsx"

BULAN_MAP = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
    9: "September", 10: "Oktober", 11: "November", 12: "Desember"
}

# =========================
# LOAD DATA
# =========================
@st.cache_data
def load_data():
    df = pd.read_excel(DATA_PATH)

    df["Date time"] = pd.to_datetime(
        df["Date time"],
        errors="coerce",
        utc=True
    ).dt.tz_localize(None)

    df["Tahun"] = df["Date time"].dt.year
    df["Bulan"] = df["Date time"].dt.month
    df["Nama Bulan"] = df["Bulan"].map(BULAN_MAP)

    # Provinsi asli hanya terisi untuk gempa yang episenternya di darat.
    # Untuk gempa di laut, provinsi terdekat dipakai sebagai wilayah acuan.
    df["Provinsi_Tampil"] = df["Provinsi"].fillna(df["Provinsi_Terdekat"])
    df["Kabupaten_Kota_Tampil"] = df["Kabupaten_Kota"].fillna(df["Kabupaten_Kota_Terdekat"])

    return df

df = load_data()

# =========================
# KARAKTERISASI CLUSTER
# =========================
# Label & warna cluster TIDAK dibuat berdasarkan urutan kedalaman semata,
# melainkan mengikuti karakter asli hasil K-Means (fitur: Magnitude,
# Depth (km), Azimuth Gap — lihat pipeline_klasterisasi_gempa.ipynb).
#
# Kategori kedalaman mengikuti konvensi umum seismologi:
#   Dangkal  : < 70 km      Menengah : 70-300 km      Dalam : > 300 km
# Kategori Azimuth Gap mengikuti konvensi kualitas penentuan episenter:
#   Gap < 180 derajat -> episenter terkonstrain baik (Presisi Tinggi)
#   Gap >= 180 derajat -> cakupan stasiun kurang merata (Presisi Rendah)
#
# Dihitung dari SELURUH data (bukan data terfilter) agar label & warna
# tiap cluster konsisten walau pengguna mengganti filter di sidebar.
def kategori_kedalaman(depth):
    if depth < 70:
        return "Dangkal"
    elif depth <= 300:
        return "Menengah"
    else:
        return "Dalam"

def kategori_presisi(gap):
    return "Presisi Tinggi" if gap < 180 else "Presisi Rendah"

_cluster_stats = (
    df.groupby("cluster_label")
    .agg(
        Magnitude_mean=("Magnitude", "mean"),
        Depth_mean=("Depth (km)", "mean"),
        Gap_mean=("Azimuth Gap", "mean"),
    )
    .reset_index()
)

_cluster_stats["Kategori_Kedalaman"] = _cluster_stats["Depth_mean"].apply(kategori_kedalaman)
_cluster_stats["Kategori_Presisi"] = _cluster_stats["Gap_mean"].apply(kategori_presisi)
_cluster_stats["Label_Karakter"] = (
    _cluster_stats["Kategori_Kedalaman"] + " · " + _cluster_stats["Kategori_Presisi"]
)
_cluster_stats["Nama_Cluster"] = (
    "Cluster " + _cluster_stats["cluster_label"].astype(str)
    + " (" + _cluster_stats["Label_Karakter"] + ")"
)

# Urutkan berdasarkan kedalaman lalu gap supaya legenda tampil konsisten
_cluster_stats = _cluster_stats.sort_values(["Depth_mean", "Gap_mean"]).reset_index(drop=True)

CLUSTER_LABEL_MAP = dict(zip(_cluster_stats["cluster_label"], _cluster_stats["Label_Karakter"]))
CLUSTER_NAME_MAP = dict(zip(_cluster_stats["cluster_label"], _cluster_stats["Nama_Cluster"]))
CLUSTER_ORDER = _cluster_stats["Nama_Cluster"].tolist()

# Palet warna semantik: hijau = dangkal & presisi tinggi, oranye = dangkal
# & presisi rendah (perlu kehati-hatian membaca lokasi episenter), biru
# keunguan = kedalaman menengah/dalam.
_WARNA_BY_KARAKTER = {
    "Dangkal · Presisi Tinggi": "#2ECC71",   # hijau
    "Dangkal · Presisi Rendah": "#E67E22",   # oranye
    "Menengah · Presisi Tinggi": "#3498DB",  # biru
    "Menengah · Presisi Rendah": "#9B59B6",  # ungu
    "Dalam · Presisi Tinggi": "#2C3E50",     # biru gelap
    "Dalam · Presisi Rendah": "#8E44AD",     # ungu gelap
}
CLUSTER_COLOR_MAP = {
    row["Nama_Cluster"]: _WARNA_BY_KARAKTER.get(row["Label_Karakter"], "#95A5A6")
    for _, row in _cluster_stats.iterrows()
}

# =========================
# SIDEBAR - FILTER UTAMA
# =========================
st.sidebar.title("🌋 Filter Dashboard")

tahun = st.sidebar.multiselect(
    "Tahun",
    sorted(df["Tahun"].dropna().unique()),
    default=sorted(df["Tahun"].dropna().unique())
)

provinsi = st.sidebar.multiselect(
    "Provinsi (asli / terdekat)",
    sorted(df["Provinsi_Tampil"].dropna().unique()),
    default=sorted(df["Provinsi_Tampil"].dropna().unique())
)

status_wilayah = st.sidebar.multiselect(
    "Status Wilayah Episenter",
    sorted(df["Status_Wilayah"].dropna().unique()),
    default=sorted(df["Status_Wilayah"].dropna().unique())
)

cluster_options = sorted(df["cluster_label"].unique())
cluster_nama_terpilih = st.sidebar.multiselect(
    "Cluster",
    options=[CLUSTER_NAME_MAP[c] for c in cluster_options],
    default=[CLUSTER_NAME_MAP[c] for c in cluster_options]
)
_nama_to_label = {v: k for k, v in CLUSTER_NAME_MAP.items()}
cluster = [str(_nama_to_label[n]) for n in cluster_nama_terpilih]

mag_range = st.sidebar.slider(
    "Magnitudo",
    float(df["Magnitude"].min()),
    float(df["Magnitude"].max()),
    (
        float(df["Magnitude"].min()),
        float(df["Magnitude"].max())
    )
)

depth_range = st.sidebar.slider(
    "Kedalaman (km)",
    int(df["Depth (km)"].min()),
    int(df["Depth (km)"].max()),
    (
        int(df["Depth (km)"].min()),
        int(df["Depth (km)"].max())
    )
)

with st.sidebar.expander("⚙️ Filter Lanjutan"):
    mag_type = st.multiselect(
        "Tipe Magnitudo (Mag Type)",
        sorted(df["Mag Type"].dropna().unique()),
        default=sorted(df["Mag Type"].dropna().unique())
    )

    jarak_max = float(df["Jarak_ke_Daratan_km"].max())
    jarak_range = st.slider(
        "Jarak ke Daratan (km, khusus gempa Laut)",
        0.0,
        jarak_max,
        (0.0, jarak_max)
    )

filtered = df[
    (df["Tahun"].isin(tahun))
    & (df["Provinsi_Tampil"].isin(provinsi))
    & (df["Status_Wilayah"].isin(status_wilayah))
    & (df["cluster_label"].astype(str).isin(cluster))
    & (df["Magnitude"].between(mag_range[0], mag_range[1]))
    & (df["Depth (km)"].between(depth_range[0], depth_range[1]))
    & (df["Mag Type"].isin(mag_type))
    & (
        (df["Status_Wilayah"] != "Laut")
        | (df["Jarak_ke_Daratan_km"].between(jarak_range[0], jarak_range[1]))
    )
]

# =========================
# HEADER
# =========================
st.title("🌋 Dashboard Clustering Gempa Bumi Indonesia")
st.markdown("Analisis Spasial, Temporal, dan Karakteristik Klaster Gempa Bumi Indonesia (2020–2025) — Sumber: BMKG")

# =========================
# KPI
# =========================
c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Total Gempa", f"{len(filtered):,}")
c2.metric("Magnitudo Maks", round(filtered["Magnitude"].max(), 2) if len(filtered) else "-")
c3.metric("Magnitudo Rata-rata", round(filtered["Magnitude"].mean(), 2) if len(filtered) else "-")
c4.metric("Kedalaman Rata-rata (km)", round(filtered["Depth (km)"].mean(), 2) if len(filtered) else "-")

pct_laut = (filtered["Status_Wilayah"] == "Laut").mean() * 100 if len(filtered) else 0
c5.metric("Episenter di Laut", f"{pct_laut:.1f}%")

# =========================
# TABS
# =========================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🗺️ Peta",
    "📊 Statistik",
    "🔥 Heatmap",
    "🎯 Analisis Cluster",
    "🌊 Wilayah Laut & Darat",
    "📋 Dataset"
])

# =====================================================
# TAB PETA
# =====================================================
with tab1:

    st.subheader("Sebaran Gempa Indonesia")

    map_style = st.selectbox(
        "Gaya Peta",
        ["satellite-streets", "open-street-map", "carto-positron", "carto-darkmatter"],
        index=0
    )

    # =================================================================
    # Warna & label cluster mengikuti karakter ASLI hasil K-Means, yaitu
    # kombinasi Kedalaman dan Azimuth Gap (kualitas presisi lokasi),
    # bukan sekadar peringkat kedalaman. Lihat blok "KARAKTERISASI
    # CLUSTER" di atas untuk definisi kategori dan sumber datanya.
    # =================================================================
    tmp = filtered.copy()
    tmp["Kategori Cluster"] = tmp["cluster_label"].map(CLUSTER_NAME_MAP)

    if len(tmp):
        fig = px.scatter_map(
            tmp,
            lat="Latitude",
            lon="Longitude",
            color="Kategori Cluster",
            category_orders={"Kategori Cluster": CLUSTER_ORDER},
            color_discrete_map=CLUSTER_COLOR_MAP,
            size="Magnitude",
            size_max=18,
            hover_name="Wilayah_Detail",
            hover_data={
                "Provinsi_Tampil": True,
                "Status_Wilayah": True,
                "Magnitude": True,
                "Depth (km)": True,
                "Tahun": True,
                "Latitude": False,
                "Longitude": False
            },
            opacity=0.8,
            zoom=4,
            center={"lat": -2.5, "lon": 118},
            title="Persebaran Gempa Berdasarkan Cluster"
        )

        fig.update_layout(
            map_style=map_style,
            margin={"r": 0, "t": 40, "l": 0, "b": 0},
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            height=600
        )

        st.plotly_chart(fig, use_container_width=True)

        rentang = (
            tmp.groupby("Kategori Cluster")[["Depth (km)", "Azimuth Gap"]]
            .agg(["min", "max"])
            .round(1)
            .reindex(CLUSTER_ORDER)
            .dropna()
        )
        ket = " | ".join(
            f"**{idx}**: kedalaman {row[('Depth (km)','min')]}–{row[('Depth (km)','max')]} km, "
            f"gap {row[('Azimuth Gap','min')]}–{row[('Azimuth Gap','max')]}°"
            for idx, row in rentang.iterrows()
        )
        st.caption(f"📌 Rentang kedalaman & azimuth gap per cluster (menyesuaikan data terfilter): {ket}")
        st.caption("💡 Azimuth Gap < 180° = episenter terkonstrain baik oleh sebaran stasiun; ≥ 180° = presisi lokasi lebih rendah. Tips: scroll untuk zoom, drag untuk geser peta, klik legenda untuk tampil/sembunyikan kategori. Nama wilayah pada popup memakai kolom **Wilayah_Detail** (untuk gempa laut menampilkan jarak ke daratan terdekat).")
    else:
        st.info("Tidak ada data yang cocok dengan filter saat ini.")

# =====================================================
# TAB STATISTIK
# =====================================================
with tab2:

    col1, col2 = st.columns(2)

    with col1:
        tahun_stat = (
            filtered.groupby("Tahun")
            .size()
            .reset_index(name="Jumlah")
        )

        fig1 = px.line(
            tahun_stat,
            x="Tahun",
            y="Jumlah",
            markers=True,
            title="Trend Gempa Tahunan"
        )
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        bulan_stat = (
            filtered.groupby(["Bulan", "Nama Bulan"])
            .size()
            .reset_index(name="Jumlah")
            .sort_values("Bulan")
        )

        fig2 = px.bar(
            bulan_stat,
            x="Nama Bulan",
            y="Jumlah",
            title="Trend Gempa Bulanan"
        )
        fig2.update_xaxes(categoryorder="array", categoryarray=list(BULAN_MAP.values()))
        st.plotly_chart(fig2, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        top_prov = (
            filtered["Provinsi_Tampil"]
            .value_counts()
            .head(20)
            .reset_index()
        )
        top_prov.columns = ["Provinsi", "count"]

        fig3 = px.bar(
            top_prov,
            x="Provinsi",
            y="count",
            title="Top 20 Provinsi (Asli/Terdekat) Berdasarkan Jumlah Gempa"
        )
        st.plotly_chart(fig3, use_container_width=True)

    with col4:
        mag_type_stat = (
            filtered["Mag Type"]
            .value_counts()
            .reset_index()
        )
        mag_type_stat.columns = ["Mag Type", "count"]

        fig4 = px.pie(
            mag_type_stat,
            names="Mag Type",
            values="count",
            title="Distribusi Tipe Magnitudo (Mag Type)",
            hole=0.4
        )
        st.plotly_chart(fig4, use_container_width=True)

# =====================================================
# TAB HEATMAP
# =====================================================
with tab3:

    st.subheader("Heatmap Tahun vs Bulan")

    heat = pd.pivot_table(
        filtered,
        index="Tahun",
        columns="Nama Bulan",
        values="Magnitude",
        aggfunc="count",
        fill_value=0
    )
    heat = heat.reindex(columns=[b for b in BULAN_MAP.values() if b in heat.columns])

    fig_heat = px.imshow(
        heat,
        text_auto=True,
        aspect="auto",
        color_continuous_scale="OrRd"
    )
    st.plotly_chart(fig_heat, use_container_width=True)

# =====================================================
# TAB ANALISIS CLUSTER
# =====================================================
with tab4:

    st.subheader("Karakteristik Tiap Cluster")
    st.caption(
        "Cluster dibentuk oleh K-Means dari 3 fitur: **Magnitude**, **Depth (km)**, dan "
        "**Azimuth Gap** (lihat `pipeline_klasterisasi_gempa.ipynb`). Tabel dan grafik di "
        "bawah menyertakan ketiganya secara konsisten — termasuk Azimuth Gap, yang justru "
        "menjadi pembeda utama antar-cluster yang kedalamannya mirip."
    )

    cluster_summary = (
        filtered.groupby("cluster_label")
        .agg({
            "Magnitude": ["mean", "std"],
            "Depth (km)": ["mean", "std"],
            "Phase Count": "mean",
            "Azimuth Gap": ["mean", "std"],
            "Latitude": "count"
        })
    )

    cluster_summary.columns = [
        "Magnitude_mean", "Magnitude_std",
        "Depth_mean", "Depth_std",
        "PhaseCount_mean",
        "AzimuthGap_mean", "AzimuthGap_std",
        "Jumlah Data"
    ]

    cluster_summary = cluster_summary.reset_index()
    cluster_summary["Karakter"] = cluster_summary["cluster_label"].map(CLUSTER_LABEL_MAP)
    cluster_summary["Nama_Cluster"] = cluster_summary["cluster_label"].map(CLUSTER_NAME_MAP)
    cluster_summary["cluster_label"] = cluster_summary["cluster_label"].astype(str)

    st.dataframe(
        cluster_summary[[
            "cluster_label", "Karakter", "Jumlah Data",
            "Magnitude_mean", "Magnitude_std",
            "Depth_mean", "Depth_std",
            "AzimuthGap_mean", "AzimuthGap_std",
            "PhaseCount_mean"
        ]].rename(columns={
            "cluster_label": "Cluster",
            "Karakter": "Karakteristik",
            "Magnitude_mean": "Rata-rata Magnitudo",
            "Magnitude_std": "Std Magnitudo",
            "Depth_mean": "Rata-rata Kedalaman (km)",
            "Depth_std": "Std Kedalaman (km)",
            "AzimuthGap_mean": "Rata-rata Azimuth Gap (°)",
            "AzimuthGap_std": "Std Azimuth Gap (°)",
            "PhaseCount_mean": "Rata-rata Phase Count"
        }).round(2),
        use_container_width=True
    )

    # ---------------------------------------------------
    # Insight otomatis per cluster (mengikuti data terfilter)
    # ---------------------------------------------------
    st.markdown("#### 🔎 Insight Karakter Cluster")
    for _, r in cluster_summary.sort_values("Depth_mean").iterrows():
        if pd.isna(r["Jumlah Data"]) or r["Jumlah Data"] == 0:
            continue
        st.markdown(
            f"- **{r['Nama_Cluster']}** — {int(r['Jumlah Data']):,} data, "
            f"magnitudo rata-rata {r['Magnitude_mean']:.2f}, kedalaman rata-rata "
            f"{r['Depth_mean']:.1f} km, azimuth gap rata-rata {r['AzimuthGap_mean']:.1f}°."
        )

    st.markdown("### Perbandingan Magnitudo, Kedalaman & Azimuth Gap per Cluster")
    st.caption("Bar chart lebih mudah dibaca dibanding boxplot: tinggi batang = rata-rata, garis di atasnya = variasi data (±1 standar deviasi). Warna cluster konsisten dengan Tab Peta.")

    colA, colB, colC = st.columns(3)

    with colA:
        fig_bar1 = px.bar(
            cluster_summary,
            x="Nama_Cluster",
            y="Magnitude_mean",
            error_y="Magnitude_std",
            color="Nama_Cluster",
            category_orders={"Nama_Cluster": CLUSTER_ORDER},
            color_discrete_map=CLUSTER_COLOR_MAP,
            text=cluster_summary["Magnitude_mean"].round(2),
            title="Rata-rata Magnitudo",
            labels={"Nama_Cluster": "Cluster", "Magnitude_mean": "Rata-rata Magnitudo"}
        )
        fig_bar1.update_traces(textposition="outside")
        fig_bar1.update_layout(showlegend=False, xaxis_title=None)
        st.plotly_chart(fig_bar1, use_container_width=True)

    with colB:
        fig_bar2 = px.bar(
            cluster_summary,
            x="Nama_Cluster",
            y="Depth_mean",
            error_y="Depth_std",
            color="Nama_Cluster",
            category_orders={"Nama_Cluster": CLUSTER_ORDER},
            color_discrete_map=CLUSTER_COLOR_MAP,
            text=cluster_summary["Depth_mean"].round(2),
            title="Rata-rata Kedalaman (km)",
            labels={"Nama_Cluster": "Cluster", "Depth_mean": "Rata-rata Kedalaman (km)"}
        )
        fig_bar2.update_traces(textposition="outside")
        fig_bar2.update_layout(showlegend=False, xaxis_title=None)
        st.plotly_chart(fig_bar2, use_container_width=True)

    with colC:
        fig_bar3 = px.bar(
            cluster_summary,
            x="Nama_Cluster",
            y="AzimuthGap_mean",
            error_y="AzimuthGap_std",
            color="Nama_Cluster",
            category_orders={"Nama_Cluster": CLUSTER_ORDER},
            color_discrete_map=CLUSTER_COLOR_MAP,
            text=cluster_summary["AzimuthGap_mean"].round(1),
            title="Rata-rata Azimuth Gap (°)",
            labels={"Nama_Cluster": "Cluster", "AzimuthGap_mean": "Rata-rata Azimuth Gap (°)"}
        )
        fig_bar3.add_hline(
            y=180, line_dash="dash", line_color="gray",
            annotation_text="Batas presisi (180°)", annotation_position="top left"
        )
        fig_bar3.update_traces(textposition="outside")
        fig_bar3.update_layout(showlegend=False, xaxis_title=None)
        st.plotly_chart(fig_bar3, use_container_width=True)

    st.markdown("### Sebaran Kedalaman vs Azimuth Gap per Titik Data")
    st.caption("Scatter ini menunjukkan mengapa cluster terbentuk seperti itu: pisahan sumbu-X (kedalaman) memisahkan Cluster yang dalam dari yang dangkal, sedangkan pisahan sumbu-Y (azimuth gap) memisahkan cluster dangkal yang presisi lokasinya baik dari yang kurang baik.")

    sample_n = min(len(filtered), 8000)
    scatter_df = filtered.sample(sample_n, random_state=42) if len(filtered) > sample_n else filtered
    scatter_df = scatter_df.copy()
    scatter_df["Nama_Cluster"] = scatter_df["cluster_label"].map(CLUSTER_NAME_MAP)

    if len(scatter_df):
        fig_scatter = px.scatter(
            scatter_df,
            x="Depth (km)",
            y="Azimuth Gap",
            color="Nama_Cluster",
            category_orders={"Nama_Cluster": CLUSTER_ORDER},
            color_discrete_map=CLUSTER_COLOR_MAP,
            opacity=0.5,
            labels={"Depth (km)": "Kedalaman (km)", "Azimuth Gap": "Azimuth Gap (°)"}
        )
        fig_scatter.add_hline(y=180, line_dash="dash", line_color="gray")
        st.plotly_chart(fig_scatter, use_container_width=True)
        if sample_n < len(filtered):
            st.caption(f"Menampilkan sampel acak {sample_n:,} dari {len(filtered):,} titik data terfilter agar peta tetap responsif.")
    else:
        st.info("Tidak ada data yang cocok dengan filter saat ini.")

    st.markdown("### Komposisi Status Wilayah per Cluster")
    status_cluster = (
        filtered.groupby(["cluster_label", "Status_Wilayah"])
        .size()
        .reset_index(name="Jumlah")
    )
    status_cluster["Nama_Cluster"] = status_cluster["cluster_label"].map(CLUSTER_NAME_MAP)

    fig_status = px.bar(
        status_cluster,
        x="Nama_Cluster",
        y="Jumlah",
        color="Status_Wilayah",
        barmode="group",
        category_orders={"Nama_Cluster": CLUSTER_ORDER},
        title="Jumlah Gempa Laut vs Darat per Cluster",
        labels={"Nama_Cluster": "Cluster"}
    )
    st.plotly_chart(fig_status, use_container_width=True)

# =====================================================
# TAB WILAYAH LAUT & DARAT
# =====================================================
with tab5:

    st.subheader("Karakteristik Wilayah Episenter")

    colL, colR = st.columns(2)

    with colL:
        status_count = filtered["Status_Wilayah"].value_counts().reset_index()
        status_count.columns = ["Status Wilayah", "Jumlah"]

        fig5 = px.pie(
            status_count,
            names="Status Wilayah",
            values="Jumlah",
            title="Proporsi Gempa Laut vs Darat",
            hole=0.4,
            color="Status Wilayah",
            color_discrete_map={"Laut": "#3498DB", "Darat": "#8B5E3C"}
        )
        st.plotly_chart(fig5, use_container_width=True)

    with colR:
        tipe_darat = (
            filtered[filtered["Status_Wilayah"] == "Darat"]["Tipe_Wilayah"]
            .value_counts()
            .reset_index()
        )
        tipe_darat.columns = ["Tipe Wilayah", "Jumlah"]

        fig6 = px.bar(
            tipe_darat,
            x="Tipe Wilayah",
            y="Jumlah",
            title="Tipe Wilayah untuk Gempa Darat",
            color="Tipe Wilayah"
        )
        fig6.update_layout(showlegend=False)
        st.plotly_chart(fig6, use_container_width=True)

    st.markdown("### Distribusi Jarak ke Daratan (khusus Gempa Laut)")
    laut_df = filtered[filtered["Status_Wilayah"] == "Laut"]

    if len(laut_df):
        fig7 = px.histogram(
            laut_df,
            x="Jarak_ke_Daratan_km",
            nbins=40,
            title="Distribusi Jarak Episenter Laut ke Daratan Terdekat (km)",
            labels={"Jarak_ke_Daratan_km": "Jarak ke Daratan (km)"}
        )
        st.plotly_chart(fig7, use_container_width=True)
        st.caption(f"Rata-rata jarak ke daratan: **{laut_df['Jarak_ke_Daratan_km'].mean():.1f} km** | Terjauh: **{laut_df['Jarak_ke_Daratan_km'].max():.1f} km** | Terdekat: **{laut_df['Jarak_ke_Daratan_km'].min():.2f} km**")
    else:
        st.info("Tidak ada data gempa laut pada filter saat ini.")

    colM, colN = st.columns(2)

    with colM:
        st.markdown("#### Top 10 Kabupaten/Kota (Gempa Darat)")
        top_kab_darat = (
            filtered[filtered["Status_Wilayah"] == "Darat"]["Kabupaten_Kota_Tampil"]
            .value_counts()
            .head(10)
        )
        st.dataframe(top_kab_darat.rename_axis("Kabupaten/Kota").reset_index(name="Jumlah"), use_container_width=True)

    with colN:
        st.markdown("#### Top 10 Kabupaten/Kota Terdekat (Gempa Laut)")
        top_kab_laut = (
            filtered[filtered["Status_Wilayah"] == "Laut"]["Kabupaten_Kota_Tampil"]
            .value_counts()
            .head(10)
        )
        st.dataframe(top_kab_laut.rename_axis("Kabupaten/Kota Terdekat").reset_index(name="Jumlah"), use_container_width=True)

# =====================================================
# TAB DATASET
# =====================================================
with tab6:

    st.subheader("Dataset Lengkap")

    search_keyword = st.text_input(
        "🔎 Cari berdasarkan keyword",
        placeholder="Contoh: nama provinsi, cluster, dll."
    )

    tampilkan_semua_kolom = st.checkbox("Tampilkan semua kolom (termasuk kolom teknis)", value=False)

    kolom_ringkas = [
        "Event ID", "Date time", "Tahun", "Nama Bulan",
        "Latitude", "Longitude", "Magnitude", "Mag Type",
        "Depth (km)", "Provinsi_Tampil", "Kabupaten_Kota_Tampil",
        "Status_Wilayah", "Tipe_Wilayah", "Jarak_ke_Daratan_km",
        "Wilayah_Detail", "cluster_label"
    ]

    dataset_view = filtered.copy() if tampilkan_semua_kolom else filtered[kolom_ringkas].copy()

    if search_keyword:
        keyword = search_keyword.strip().lower()

        mask = pd.Series(False, index=dataset_view.index)

        for col in dataset_view.columns:
            mask = mask | dataset_view[col].astype(str).str.lower().str.contains(keyword, na=False)

        dataset_view = dataset_view[mask]

    st.caption(f"Menampilkan {len(dataset_view):,} dari {len(filtered):,} data hasil filter sidebar.")

    st.dataframe(
        dataset_view,
        use_container_width=True,
        height=500
    )

    # ---------------------------------------------------
    # Export CSV & Excel
    # ---------------------------------------------------
    # Dua perbaikan di sini untuk mengatasi error "not connected to a
    # server!" pada tombol download:
    #   1. Bytes CSV/Excel di-cache (bukan dibangun ulang tiap rerun),
    #      supaya proses generate file besar tidak lama-lama membuka
    #      koneksi saat browser sedang meminta URL download-nya.
    #   2. Setiap download_button diberi `key` unik berbasis isi data,
    #      supaya widget tidak bentrok/"nyangkut" antar-rerun ketika
    #      filter atau kata kunci pencarian berubah.
    def _dataset_cache_key(data):
        try:
            return int(pd.util.hash_pandas_object(data, index=True).sum())
        except Exception:
            return f"{len(data)}_{tuple(data.columns)}"

    @st.cache_data(show_spinner=False)
    def _build_csv_bytes(_data, cache_key):
        return _data.to_csv(index=False).encode("utf-8")

    @st.cache_data(show_spinner=False)
    def _build_excel_bytes(_data, cache_key):
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            _data.to_excel(writer, index=False)
        return buf.getvalue()

    cache_key = _dataset_cache_key(dataset_view)

    csv_bytes = _build_csv_bytes(dataset_view, cache_key)
    excel_bytes = _build_excel_bytes(dataset_view, cache_key)

    colDL1, colDL2 = st.columns(2)

    with colDL1:
        st.download_button(
            "⬇️ Download CSV",
            csv_bytes,
            "dataset_gempa.csv",
            "text/csv",
            key=f"download_csv_{cache_key}",
            use_container_width=True
        )

    with colDL2:
        st.download_button(
            "⬇️ Download Excel",
            excel_bytes,
            "dataset_gempa.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_excel_{cache_key}",
            use_container_width=True
        )

    st.caption("⚠️ Jika tombol download menampilkan error \"not connected to a server\", refresh halaman (F5) lalu klik ulang — ini terjadi saat koneksi ke server sempat terputus, bukan karena data rusak.")
