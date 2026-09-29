# Panduan Integrasi Supabase Storage — BananaVision

Dokumen ini menjelaskan langkah-langkah untuk menyiapkan dan menghubungkan **Supabase Storage** sebagai media penyimpanan cloud model AI (`.keras`) Anda di lingkungan production.

---

## 1. Konfigurasi di Dashboard Supabase

Ikuti langkah berikut di [Supabase Console](https://supabase.com/):

### Langkah 1: Buat Bucket Baru
1. Masuk ke dashboard proyek Supabase Anda.
2. Klik menu **Storage** di sidebar kiri.
3. Klik tombol **New bucket**.
4. Beri nama bucket: **`models`** (atau sesuaikan dengan nama yang Anda inginkan).
5. Biarkan bucket sebagai **Private**. Backend membuat signed URL sementara untuk FastAPI.
6. Atur batas ukuran bucket lebih besar dari ukuran model yang akan diunggah, lalu klik **Save**.

Supabase Free membatasi ukuran file maksimal **50 MB**. Model ResNet di atas 100 MB memerlukan Pro atau paket lebih tinggi; setelah upgrade, atur global dan batas bucket agar lebih besar dari ukuran model.

### Langkah 2: Atur Policies (Kebijakan Akses)
Upload dan pembuatan signed URL dilakukan backend menggunakan service-role key. Jangan menaruh key ini di frontend atau commit ke repository.

---

## 2. Instalasi Dependency pada Backend Node.js
Buka terminal Anda, masuk ke folder `backend/`, lalu jalankan perintah berikut untuk menginstal SDK resmi Supabase:

```bash
cd backend
npm install
```

---

## 3. Tambahkan Environment Variables
Buka file `backend/.env` Anda dan tambahkan konfigurasi Supabase berikut:

```env
# Supabase Configuration
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
SUPABASE_BUCKET=models
MODEL_SYNC_TOKEN=<shared-secret-for-python-to-query-active-model>
```

---

## 4. Alur Kerja Sistem (Bagaimana Ini Bekerja?)

1. **Admin** mengunggah file model (`.keras`) di panel admin.
2. **Node.js Backend** mengunggah file `.keras` ke bucket Supabase menggunakan TUS resumable upload (chunk 6 MB), lalu menyimpan metadata model di MongoDB.
3. Saat model diaktifkan, Node.js membuat signed URL sementara lalu mengirimkannya ke FastAPI pada `/api/reload`.
4. FastAPI mengunduh model ke `MODEL_DIR` lalu memuatnya ke memori TensorFlow.

Kedua service Railway memiliki filesystem terpisah. Untuk menyimpan cache model setelah restart, tambahkan Volume ke service **FastAPI** dengan mount path `/data/models` dan atur `MODEL_DIR=/data/models`. Supabase tetap menjadi penyimpanan permanen sumber model.

Atur URL komunikasi di Railway:
- Service Express: `ML_SERVER_URL=https://<domain-fastapi>`
- Service Express and FastAPI: use the same random value for `MODEL_SYNC_TOKEN`
- Service FastAPI: `NODE_BACKEND_URL=https://<domain-express>/api`

---

## 5. Sinkronisasi Saat Server Python Restart
Saat startup, FastAPI memakai cache di volume jika model sudah tersedia. Jika belum, FastAPI meminta metadata model aktif dari Express; Express membuat signed URL baru dan FastAPI mengunduh model dari Supabase. Atur perintah start Railway ke `uvicorn server:app --host 0.0.0.0 --port $PORT`.
