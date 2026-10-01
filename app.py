# ==========================================================
# DASHBOARD CLUSTERING GEMPA BUMI INDONESIA
# Versi Skripsi Premium (disesuaikan dengan df_final_fix.xlsx)
# ==========================================================

import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO

st.set_page_config(
    page_title="Dashboard Gempa Indonesia",
    page_icon="🌋",
    layout="wide"
)

# =========================
# CONFIG
# =========================
DATA_PATH = "df_Revisi.xlsx"

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

cluster = st.sidebar.multiselect(
    "Cluster",
    sorted(df["cluster_label"].astype(str).unique()),
    default=sorted(df["cluster_label"].astype(str).unique())
)

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
    # Warna & label cluster ditentukan otomatis dari rata-rata kedalaman
    # tiap cluster pada keseluruhan data: paling dangkal = hijau (Rendah),
    # menengah = kuning (Sedang), paling dalam = merah (Tinggi).
    # =================================================================
    cluster_depth_rank = (
        df.groupby("cluster_label")["Depth (km)"]
        .mean()
        .sort_values()
        .index.tolist()
    )

    label_map = {
        cluster_depth_rank[0]: "Rendah",
        cluster_depth_rank[1]: "Sedang",
        cluster_depth_rank[2]: "Tinggi"
    }

    color_map = {
        "Rendah": "#2ECC71",  # Hijau
        "Sedang": "#F1C40F",  # Kuning
        "Tinggi": "#E74C3C"   # Merah
    }

    tmp = filtered.copy()
    tmp["Kategori Cluster"] = tmp["cluster_label"].map(label_map)

    if len(tmp):
        fig = px.scatter_map(
            tmp,
            lat="Latitude",
            lon="Longitude",
            color="Kategori Cluster",
            category_orders={"Kategori Cluster": ["Rendah", "Sedang", "Tinggi"]},
            color_discrete_map=color_map,
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
            tmp.groupby("Kategori Cluster")["Depth (km)"]
            .agg(["min", "max"])
            .round(2)
            .reindex(["Rendah", "Sedang", "Tinggi"])
            .dropna()
        )
        ket = " | ".join(
            f"**{idx}**: {row['min']}–{row['max']} km"
            for idx, row in rentang.iterrows()
        )
        st.caption(f"📌 Rentang kedalaman per cluster (otomatis menyesuaikan data terfilter): {ket}")
        st.caption("💡 Tips: scroll untuk zoom, drag untuk geser peta, klik legenda untuk tampil/sembunyikan kategori. Nama wilayah pada popup memakai kolom **Wilayah_Detail** (untuk gempa laut menampilkan jarak ke daratan terdekat).")
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

    cluster_summary = (
        filtered.groupby("cluster_label")
        .agg({
            "Magnitude": ["mean", "std"],
            "Depth (km)": ["mean", "std"],
            "Phase Count": "mean",
            "Azimuth Gap": "mean",
            "Latitude": "count"
        })
    )

    cluster_summary.columns = [
        "Magnitude_mean", "Magnitude_std",
        "Depth_mean", "Depth_std",
        "PhaseCount_mean", "AzimuthGap_mean",
        "Jumlah Data"
    ]

    cluster_summary = cluster_summary.reset_index()
    cluster_summary["cluster_label"] = cluster_summary["cluster_label"].astype(str)

    st.dataframe(
        cluster_summary.rename(columns={
            "cluster_label": "Cluster",
            "Magnitude_mean": "Rata-rata Magnitudo",
            "Magnitude_std": "Std Magnitudo",
            "Depth_mean": "Rata-rata Kedalaman (km)",
            "Depth_std": "Std Kedalaman (km)",
            "PhaseCount_mean": "Rata-rata Phase Count",
            "AzimuthGap_mean": "Rata-rata Azimuth Gap"
        }).round(2),
        use_container_width=True
    )

    st.markdown("### Perbandingan Rata-rata Magnitudo & Kedalaman per Cluster")
    st.caption("Bar chart lebih mudah dibaca dibanding boxplot: tinggi batang = rata-rata, garis di atasnya = variasi data (±1 standar deviasi).")

    colA, colB = st.columns(2)

    with colA:
        fig_bar1 = px.bar(
            cluster_summary,
            x="cluster_label",
            y="Magnitude_mean",
            error_y="Magnitude_std",
            color="cluster_label",
            text=cluster_summary["Magnitude_mean"].round(2),
            title="Rata-rata Magnitudo per Cluster",
            labels={"cluster_label": "Cluster", "Magnitude_mean": "Rata-rata Magnitudo"}
        )
        fig_bar1.update_traces(textposition="outside")
        fig_bar1.update_layout(showlegend=False)
        st.plotly_chart(fig_bar1, use_container_width=True)

    with colB:
        fig_bar2 = px.bar(
            cluster_summary,
            x="cluster_label",
            y="Depth_mean",
            error_y="Depth_std",
            color="cluster_label",
            text=cluster_summary["Depth_mean"].round(2),
            title="Rata-rata Kedalaman per Cluster",
            labels={"cluster_label": "Cluster", "Depth_mean": "Rata-rata Kedalaman (km)"}
        )
        fig_bar2.update_traces(textposition="outside")
        fig_bar2.update_layout(showlegend=False)
        st.plotly_chart(fig_bar2, use_container_width=True)

    st.markdown("### Komposisi Status Wilayah per Cluster")
    status_cluster = (
        filtered.groupby(["cluster_label", "Status_Wilayah"])
        .size()
        .reset_index(name="Jumlah")
    )
    status_cluster["cluster_label"] = status_cluster["cluster_label"].astype(str)

    fig_status = px.bar(
        status_cluster,
        x="cluster_label",
        y="Jumlah",
        color="Status_Wilayah",
        barmode="group",
        title="Jumlah Gempa Laut vs Darat per Cluster",
        labels={"cluster_label": "Cluster"}
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

    csv = dataset_view.to_csv(index=False).encode("utf-8")

    st.download_button(
        "⬇️ Download CSV",
        csv,
        "dataset_gempa.csv",
        "text/csv"
    )

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataset_view.to_excel(writer, index=False)

    st.download_button(
        "⬇️ Download Excel",
        output.getvalue(),
        "dataset_gempa.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )