# Frontend BananaVision

Frontend aplikasi BananaVision dibangun menggunakan React dan Vite.

## Instalasi

```bash
cd frontend
npm install
```

## Konfigurasi

Salin `frontend/.env.example` ke `frontend/.env` dan isi:

- `VITE_API_BASE_URL`
- `VITE_FIREBASE_API_KEY`
- `VITE_FIREBASE_AUTH_DOMAIN`
- `VITE_FIREBASE_PROJECT_ID`
- `VITE_FIREBASE_APP_ID`

## Menjalankan development

```bash
npm run dev
```

## Build produksi

```bash
npm run build
```

## Deploy ke Vercel

Untuk deploy frontend ke Vercel:

1. Pastikan project yang dipilih adalah folder `frontend`.
2. Set environment variables di dashboard Vercel:
   - `VITE_API_BASE_URL=https://bananavisionv3-production-12ee.up.railway.app/api`
   - `VITE_FIREBASE_API_KEY`
   - `VITE_FIREBASE_AUTH_DOMAIN`
   - `VITE_FIREBASE_PROJECT_ID`
   - `VITE_FIREBASE_APP_ID`
3. Biarkan `Build Command` tetap `npm run build` dan `Output Directory` tetap `dist`.
4. Setelah mengubah environment variable, lakukan redeploy agar nilai baru masuk ke bundle.

Juga tersedia file `frontend/vercel.json` untuk konfigurasi build Vercel.

## Fitur utama

- Login Google saja
- Halaman dashboard analisis penyakit pisang
- Penyimpanan riwayat analisis
- Data penyakit dan rekomendasi penanganan
- PWA/Service Worker untuk pengalaman offline

## Catatan

Frontend saat ini menggunakan token JWT yang disimpan di `localStorage`.
