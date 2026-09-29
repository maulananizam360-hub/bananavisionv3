# API Reference — BananaVision v3.1

Base URL Production: `https://bananavisionv3-production-12ee.up.railway.app/api`
Base URL Local: `http://localhost:5000/api`

Semua endpoint yang membutuhkan autentikasi user harus menyertakan header:
```http
Authorization: Bearer <jwt-token>
```

Semua endpoint yang membutuhkan autentikasi admin:
```http
Authorization: Bearer <admin-jwt-token>
```

Response format:
```json
{ "success": true, "data": {}, "message": "..." }
{ "success": false, "message": "..." }
```

---

## Auth (User)

### POST /api/auth/google
Login dengan Google Firebase ID Token.

**Body:**
```json
{ "idToken": "<firebase-id-token>" }
```

**Response:**
```json
{
  "data": {
    "user": { "id": "...", "email": "...", "name": "...", "avatar": "..." },
    "token": "<jwt>"
  }
}
```

---

### GET /api/auth/profile 🔒
Ambil profil user yang sedang login.

**Response:** `{ "data": { "id", "email", "name", "avatar", "createdAt", "lastLoginAt", "notifications", "language" } }`

---

### PUT /api/auth/profile 🔒
Update profil user.

**Body:** `{ "name": "...", "notifications": true, "language": "id" }`

---

### GET /api/auth/verify 🔒
Cek apakah JWT masih valid.

**Response:** `{ "success": true, "message": "Token is valid" }`

---

## Analyses

### POST /api/analyses/analyze 🔒
Analisis gambar daun pisang.

**Body:**
```json
{
  "imageBase64": "<base64-string-tanpa-prefix-data:image>",
  "notes": "catatan opsional"
}
```

**Response (Sukses):**
```json
{
  "data": {
    "id": "...",
    "detectedDisease": "Black Sigatoka",
    "confidence": 95.0,
    "category": "Jamur",
    "severity": "Berat",
    "status": "completed",
    "is_banana": true,
    "predictions": [
      { "disease": "Black Sigatoka", "confidence": 95.0 },
      { "disease": "Healthy Leaf", "confidence": 3.0 }
    ],
    "createdAt": "2026-01-01T00:00:00Z"
  }
}
```

**Response (Bukan Daun Pisang):**
```json
{
  "data": {
    "detectedDisease": "Bukan Daun/Batang Pisang",
    "is_banana": false,
    "confidence": 0
  }
}
```

> **Catatan:**
> - `status` bisa `completed` atau `failed` (jika ML server tidak dapat diakses).
> - Gambar tidak disimpan di database (`imageUrl = null`).
> - Jika `is_banana === false`, frontend menampilkan pesan khusus tanpa menyimpan analisis.

---

### GET /api/analyses 🔒
Ambil semua riwayat analisis milik user (soft-deleted tidak tampil).

**Response:** `{ "data": [ ...analyses ] }`

---

### GET /api/analyses/:id 🔒
Ambil detail analisis spesifik.

---

### DELETE /api/analyses/:id 🔒
Hapus analisis (soft delete — set `isDeleted = true`).

---

### GET /api/analyses/dashboard/stats 🔒
Statistik dashboard user.

**Response:**
```json
{
  "data": {
    "totalAnalyses": 25,
    "healthyCount": 10,
    "diseasePrevalence": 60.0,
    "avgConfidence": 91.3
  }
}
```

---

### GET /api/analyses/dashboard/trends 🔒
Data tren analisis per periode.

**Query:** `?period=7d` | `30d` | `1y`

**Response:**
```json
{
  "data": [
    { "day": "Sen", "date": "2026-01-01", "count": 3 },
    { "day": "Sel", "date": "2026-01-02", "count": 5 }
  ]
}
```

---

## Diseases (Publik)

> Data penyakit dikelola via Admin Panel. Endpoint publik hanya READ.

### GET /api/diseases
Ambil semua data penyakit aktif. Publik, tidak perlu auth.

**Query:** `?category=Jamur` (opsional)

**Response:**
```json
{
  "data": [
    {
      "id": "...",
      "name": "Black Sigatoka",
      "description": "...",
      "category": "Jamur",
      "severity": "Berat",
      "symptoms": ["..."],
      "prevention": ["..."],
      "treatment": ["..."],
      "isActive": true
    }
  ]
}
```

### GET /api/diseases/:id
Detail penyakit berdasarkan ID. Publik.

---

## Feedback

### POST /api/feedbacks 🔒
Kirim feedback.

**Body:** `{ "message": "...", "rating": 5 }`

---

### GET /api/feedbacks
Ambil semua feedback (publik).

---

## Admin

> Semua endpoint `/api/admin/*` (kecuali login dan `active-info`) memerlukan **Admin JWT**.

### POST /api/admin/login
Login admin dengan email & password (bukan Firebase).

**Body:**
```json
{ "email": "admin@example.com", "password": "password" }
```

**Response:**
```json
{
  "data": {
    "admin": { "id": "...", "email": "...", "name": "...", "role": "admin" },
    "token": "<admin-jwt>"
  }
}
```

---

### GET /api/admin/profile 🔒Admin
Profil admin yang sedang login.

---

### GET /api/admin/stats 🔒Admin
Statistik global sistem (untuk admin dashboard).

**Response:**
```json
{
  "data": {
    "totalUsers": 150,
    "totalAnalyses": 1230,
    "totalDiseases": 7,
    "totalFeedbacks": 45
  }
}
```

---

## Admin: Diseases

### GET /api/admin/diseases 🔒Admin
Daftar semua penyakit (termasuk yang nonaktif).

### POST /api/admin/diseases 🔒Admin
Tambah penyakit baru.

**Body:**
```json
{
  "name": "Nama Penyakit",
  "description": "Deskripsi...",
  "category": "Jamur",
  "severity": "Berat",
  "symptoms": ["gejala 1", "gejala 2"],
  "prevention": ["pencegahan 1"],
  "treatment": ["penanganan 1"],
  "imageUrl": "https://..."
}
```

### PUT /api/admin/diseases/:id 🔒Admin
Update data penyakit.

### DELETE /api/admin/diseases/:id 🔒Admin
Hapus penyakit (hard delete).

### PUT /api/admin/diseases/:id/toggle 🔒Admin
Toggle `isActive` penyakit (aktif ↔ nonaktif).

---

## Admin: ML Models

### GET /api/admin/models 🔒Admin
Daftar semua model ML yang terdaftar di database.

**Response:**
```json
{
  "data": [
    {
      "id": "...",
      "name": "MobileNetV2 Final",
      "filename": "model_mobilenetv2_final.keras",
      "modelType": "mobilenetv2",
      "isActive": true,
      "fileSize": 14000000,
      "uploadedAt": "2026-06-01T00:00:00Z"
    }
  ]
}
```

### GET /api/admin/models/health 🔒Admin
Status kesehatan ML server (apakah model loaded, gatekeeper loaded, dll).

### POST /api/admin/models/upload 🔒Admin
Upload file model `.keras` baru.

**Body:** `multipart/form-data` dengan field `modelFile` (file `.keras`, max 250MB).

### PUT /api/admin/models/:id/activate 🔒Admin
Aktifkan model ML. Backend akan:
1. Update `isActive` di database
2. Call ML Server `POST /api/reload` untuk hot-swap model tanpa restart

### DELETE /api/admin/models/:id 🔒Admin
Hapus model ML dari database (dan file di disk jika ada).

### GET /api/admin/models/active-info *(publik)*
Info model aktif saat ini. Digunakan oleh Python ML server saat startup untuk auto-recovery.

**Response:**
```json
{
  "data": {
    "filename": "model_mobilenetv2_final.keras",
    "modelType": "mobilenetv2",
    "url": "https://supabase-storage-url/..."
  }
}
```

---

## Error Codes

| Status | Arti |
|---|---|
| 400 | Request tidak valid / field kosong |
| 401 | Token tidak ada atau kadaluarsa |
| 403 | Akses ditolak (bukan admin / bukan pemilik resource) |
| 404 | Data tidak ditemukan |
| 409 | Data duplikat (Prisma P2002) |
| 503 | ML Server dalam mode STANDBY (belum ada model aktif) |
| 500 | Server error |
