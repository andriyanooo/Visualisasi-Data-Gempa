# 🌏 Panduan Lengkap: Visualisasi Peta Sebaran Gempa dengan Streamlit

## 📁 Struktur Folder
```
earthquake_clustering_app/
├── app.py                  ← Aplikasi utama Streamlit
├── requirements.txt        ← Daftar library yang dibutuhkan
├── df_with_clusters.xlsx   ← File data Anda (taruh di sini)
└── README.md               ← Panduan ini
```

---

## ✅ LANGKAH 1 – Persiapan Lingkungan

### A. Pastikan Python sudah terinstall
```bash
python --version
# Pastikan versi Python 3.9 ke atas
```

### B. Buat Virtual Environment (sangat dianjurkan)
```bash
# Buat virtual environment
python -m venv venv

# Aktifkan (Windows)
venv\Scripts\activate

# Aktifkan (Mac / Linux)
source venv/bin/activate
```

---

## ✅ LANGKAH 2 – Install Library

```bash
pip install -r requirements.txt
```

Library yang diinstall:
| Library | Fungsi |
|---|---|
| `streamlit` | Framework utama web app |
| `pandas` | Baca & manipulasi data Excel |
| `openpyxl` | Engine baca file .xlsx |
| `folium` | Peta interaktif berbasis Leaflet |
| `streamlit-folium` | Integrasi Folium ke Streamlit |
| `plotly` | Grafik & chart interaktif |
| `numpy` | Komputasi numerik |

---

## ✅ LANGKAH 3 – Siapkan File Data

Salin file `df_with_clusters.xlsx` ke dalam folder `earthquake_clustering_app/`.

Pastikan file memiliki kolom berikut:
- `Latitude` → koordinat lintang
- `Longitude` → koordinat bujur
- `Magnitude` → kekuatan gempa
- `Depth (km)` → kedalaman gempa
- `cluster_label` → hasil K-Means (0, 1, atau 2)
- `Date time` → waktu kejadian
- `Location` → nama lokasi

---

## ✅ LANGKAH 4 – Jalankan Aplikasi

```bash
# Masuk ke folder proyek
cd earthquake_clustering_app

# Jalankan Streamlit
streamlit run app.py
```

Aplikasi otomatis terbuka di browser: **http://localhost:8501**

---

## ✅ LANGKAH 5 – Gunakan Fitur Aplikasi

### 🗺️ Tab "Peta Sebaran"
- **Marker Cluster** → titik gempa dikelompokkan, klik untuk detail
- **Heatmap** → area dengan konsentrasi gempa tinggi ditampilkan sebagai "panas"
- **Scatter Plot** → titik individual berukuran sesuai magnitude

### 📊 Tab "Statistik"
- Tabel statistik per cluster (rata-rata, maks, min)
- Pie chart proporsi gempa per cluster
- Box plot distribusi magnitude

### 📈 Tab "Grafik"
- Histogram magnitude & kedalaman
- Scatter plot Kedalaman vs Magnitude
- Tren gempa per bulan (time series)

### 📋 Tab "Data Tabel"
- Lihat & filter data langsung
- Download data yang sudah difilter ke CSV

### ⚙️ Sidebar (Filter)
- Upload file Excel Anda sendiri
- Pilih cluster yang ditampilkan
- Filter rentang magnitude & kedalaman
- Pilih tipe peta
- Atur jumlah sampel titik di peta

---

## ✅ LANGKAH 6 – Deploy ke Streamlit Cloud (Opsional)

### A. Upload ke GitHub
```bash
git init
git add .
git commit -m "Aplikasi Visualisasi Gempa"
git remote add origin https://github.com/username/nama-repo.git
git push -u origin main
```

### B. Deploy di Streamlit Community Cloud
1. Buka https://share.streamlit.io
2. Login dengan akun GitHub
3. Klik **"New app"**
4. Pilih repo GitHub Anda
5. Set **Main file path**: `app.py`
6. Klik **Deploy**

> ⚠️ Catatan: Untuk Streamlit Cloud, upload file Excel melalui fitur **drag & drop** di sidebar aplikasi karena file lokal tidak tersedia di server cloud.

---

## 🔧 Troubleshooting

| Masalah | Solusi |
|---|---|
| `ModuleNotFoundError` | Jalankan `pip install -r requirements.txt` |
| Peta tidak muncul | Pastikan `streamlit-folium` versi terbaru: `pip install streamlit-folium --upgrade` |
| File tidak terbaca | Pastikan `df_with_clusters.xlsx` ada di folder yang sama dengan `app.py` |
| Aplikasi lambat | Kurangi jumlah sampel di slider sidebar |

---

## 🎨 Kustomisasi Cluster

Edit bagian `CLUSTER_CONFIG` di `app.py` untuk mengubah nama dan warna cluster:

```python
CLUSTER_CONFIG = {
    0: {"label": "Cluster 0 – Gempa Dangkal",  "color": "#E74C3C", "folium_color": "red"},
    1: {"label": "Cluster 1 – Gempa Menengah", "color": "#F39C12", "folium_color": "orange"},
    2: {"label": "Cluster 2 – Gempa Dalam",    "color": "#2980B9", "folium_color": "blue"},
}
```

Warna Folium yang tersedia: `red`, `blue`, `green`, `purple`, `orange`, `darkred`, `lightred`, `beige`, `darkblue`, `darkgreen`, `cadetblue`, `lightblue`, `gray`, `black`, `lightgray`
