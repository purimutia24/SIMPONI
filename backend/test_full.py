"""
Test komprehensif SIMPONI API — jalankan dengan:
  source venv/bin/activate
  rm -f simponi.db && uvicorn app.main:app &
  sleep 2 && python3 test_full.py
  kill %1
"""
import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

# ─── Tunggu server siap (jika baru distart) ──────────────────────────────────
import time, socket
from urllib.parse import urlparse
BASE = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8001")
TEST_PORT = urlparse(BASE).port or 80
for _ in range(10):
    try:
        socket.create_connection(("127.0.0.1", TEST_PORT), timeout=1).close()
        break
    except OSError:
        time.sleep(0.5)
else:
    print("❌ Server tidak berjalan di port 8001. Jalankan uvicorn dulu!")
    sys.exit(1)

OK = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

def req(method, path, body=None, token=None, content_type="application/json"):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        res = urllib.request.urlopen(r)
        return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"error": body.decode(errors="ignore")}

def form_req(path, fields: dict, token=None):
    url = BASE + path
    data = urllib.parse.urlencode(fields).encode("utf-8")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        res = urllib.request.urlopen(r)
        return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"error": body.decode(errors="ignore")}

def check(label, code, data, expect_code=200):
    icon = OK if code == expect_code else FAIL
    print(f"  {icon} [{code}] {label}")
    if code != expect_code:
        print(f"       Detail: {data}")
    return code == expect_code

results = []
print("\n" + "="*60)
print("  SIMPONI API — Full Integration Test")
print("="*60)

# ─── Health ──────────────────────────────────────────────────────
print("\n[1] Health Check")
c, d = req("GET", "/")
results.append(check("Root endpoint", c, d))
c, d = req("GET", "/health")
results.append(check("Health endpoint (DB connected)", c, d))
assert d.get("database") == "connected", f"DB not connected: {d}"

# ─── Auth Masyarakat ─────────────────────────────────────────────
print("\n[2] Auth Masyarakat (Publik)")
from app.database import SessionLocal
from app.models import User as UserModel
from app.security import hash_password

db = SessionLocal()
db.add(UserModel(
    nik="3205112233445566",
    email="budi@test.com",
    full_name="Budi Santoso",
    password_hash=hash_password("password123"),
    kode_kabupaten=3205,
    is_active=True,
    email_verified=True,
))
db.commit()
db.close()

c, d = req("POST", "/api/v1/auth/login", {"identity": "budi@test.com", "password": "password123"})
results.append(check("Login masyarakat", c, d))
pub_token = d.get("access_token")

c, d = req("POST", "/api/v1/auth/login", {"identity": "budi@test.com", "password": "password123"})
results.append(check("Login masyarakat via email", c, d))

c, d = req("GET", "/api/v1/auth/me", token=pub_token)
results.append(check("GET /auth/me", c, d))

# ─── Forgot Password ───────────────────────────────────────────────
print("\n[3] Lupa Kata Sandi")
c, d = req("POST", "/api/v1/auth/forgot-password", {"email": "unknown@test.invalid"})
results.append(check("Forgot password keeps response generic", c, d))
assert "reset_token" not in d, "Token pemulihan tidak boleh dikembalikan di response"

# ─── Laporan ─────────────────────────────────────────────────────
print("\n[4] Laporan Masyarakat")
c, d = form_req("/api/v1/reports", {
    "pelapor_nama": "Budi Santoso",
    "pelapor_nik": "3205112233445566",
    "pelapor_telepon": "08123456789",
    "pelapor_email": "budi@test.com",
    "pelapor_domisili": "Kabupaten Garut",
    "hubungan_pelapor": "Tetangga/Masyarakat Sekitar",
    "usia_perempuan": "15 Tahun",
    "usia_laki_laki": "18 Tahun",
    "status_pendidikan": "Putus Sekolah (SMP)",
    "lokasi_kabupaten": "Kabupaten Garut",
    "lokasi_kecamatan_desa": "Kecamatan Tarogong Kaler, Desa Sukajaya",
    "waktu_rencana_akad": "25/10/2024",
    "faktor_pendorong": "Tekanan / Paksaan Orang Tua",
    "description": "Saya mengetahui seorang anak perempuan usia 15 tahun yang akan dinikahkan paksa oleh orang tuanya karena alasan ekonomi. Pernikahan direncanakan akhir bulan ini.",
    "pernyataan_benar": "true",
    "setuju_pemrosesan": "true",
}, token=pub_token)
results.append(check("Buat laporan (form data)", c, d, 201))
report_id = d.get("id")
assert d.get("status") == "Diajukan", f"Status awal harus Diajukan: {d}"
assert len(d.get("histories", [])) == 1, "Harus ada 1 history awal"
print(f"       Report ID: {report_id}, status: {d.get('status')}, histories: {len(d.get('histories', []))} ✓")

c, d = req("GET", "/api/v1/reports/mine", token=pub_token)
results.append(check("GET /reports/mine (riwayat masyarakat)", c, d))
assert len(d) >= 1

c, d = req("GET", f"/api/v1/reports/{report_id}", token=pub_token)
results.append(check(f"GET /reports/{report_id} (detail laporan)", c, d))

# ─── Setup Admin Pemprov ──────────────────────────────────────────
print("\n[5] Admin Pemprov")
# Buat via DB langsung karena tidak ada env var
from app.database import SessionLocal
from app.models import User as UserModel
from app.security import hash_password
db = SessionLocal()
prov = UserModel(nip="199001012020010001", email="adminprov@simponi.id",
    full_name="Admin Pemprov", password_hash=hash_password("pemprov123"), role="admin_pemprov")
db.add(prov)
db.commit()
db.refresh(prov)
db.close()

c, d = req("POST", "/api/v1/auth/login/admin-pemprov", {"identity": "adminprov@simponi.id", "password": "pemprov123"})
results.append(check("Login Admin Pemprov", c, d))
prov_token = d.get("access_token")

c, d = req("POST", "/api/v1/admin/provincial-admins", {
    "nip": "199101012021010001",
    "full_name": "Admin Pemprov Kedua",
    "email": "adminprov2@simponi.id",
    "password": "pemprov456",
}, token=prov_token)
results.append(check("Buat akun Admin Pemprov (oleh Pemprov)", c, d, 201))

c, d = req("GET", "/api/v1/admin/provincial-admins", token=prov_token)
results.append(check("List semua Admin Pemprov", c, d))
assert len(d) >= 2 and any(admin.get("nip") == "199101012021010001" for admin in d), d

c, d = req("POST", "/api/v1/auth/login/admin-pemprov", {"identity": "199101012021010001", "password": "pemprov456"})
results.append(check("Login Admin Pemprov via NIP", c, d))

# Buat akun Admin Pemda Garut
c, d = req("POST", "/api/v1/admin/officers", {
    "nip": "198501012010010001",
    "full_name": "Petugas Garut",
    "email": "garut@pemda.id",
    "password": "garut123",
    "kode_kabupaten": 3205
}, token=prov_token)
results.append(check("Buat akun Admin Pemda (oleh Pemprov)", c, d, 201))
officer_id = d.get("id")

c, d = req("GET", "/api/v1/admin/officers", token=prov_token)
results.append(check("List Admin Pemda (oleh Pemprov)", c, d))
assert len(d) >= 1

# ─── Admin Pemda (Garut) ──────────────────────────────────────────
print("\n[6] Admin Pemda Garut")
c, d = req("POST", "/api/v1/auth/login/admin-pemda", {"identity": "198501012010010001", "password": "garut123"})
results.append(check("Login Admin Pemda (via NIP)", c, d))
pemda_token = d.get("access_token")

c, d = req("GET", "/api/v1/admin/dashboard", token=pemda_token)
results.append(check("Dashboard Admin Pemda", c, d))
assert d.get("scope") == 3205, "Scope harus kode kabupaten Garut"
print(f"       Scope: {d.get('nama_scope')}, Total laporan: {d.get('total')}, Antrian: {d.get('queue')}")

c, d = req("GET", "/api/v1/reports", token=pemda_token)
results.append(check("List laporan masuk Pemda Garut", c, d))
assert len(d) >= 1, "Harus ada laporan dari masyarakat Garut"

# Update status laporan
c, d = req("PATCH", f"/api/v1/reports/{report_id}",
    {"status": "Diverifikasi", "note": "Laporan diterima dan diverifikasi. Pelapor akan dihubungi dalam 1x24 jam."},
    token=pemda_token)
results.append(check("Update status → Diverifikasi", c, d))
assert d.get("status") == "Diverifikasi"
assert len(d.get("histories", [])) == 2, "Harus ada 2 history (dibuat + diverifikasi)"

c, d = req("PATCH", f"/api/v1/reports/{report_id}",
    {"status": "Diproses", "note": "Kasus sedang diproses. Kunjungan lapangan dijadwalkan Kamis 31 Oktober 2024."},
    token=pemda_token)
results.append(check("Update status → Diproses", c, d))

c, d = req("PATCH", f"/api/v1/reports/{report_id}",
    {"status": "Selesai", "note": "Pendampingan selesai. Pernikahan berhasil dicegah. Anak kembali bersekolah."},
    token=pemda_token)
results.append(check("Update status → Selesai", c, d))
assert len(d.get("histories", [])) == 4
print(f"       Total histories: {len(d.get('histories', []))} ✓")

# ─── Dashboard Pemprov ────────────────────────────────────────────
print("\n[7] Dashboard Pemprov (Rapor Kabupaten)")
c, d = req("GET", "/api/v1/admin/dashboard", token=prov_token)
results.append(check("Dashboard Admin Pemprov (agregat Jawa Barat)", c, d))
assert d.get("scope") == "Jawa Barat"

c, d = req("GET", "/api/v1/admin/dashboard/rapor-kabupaten", token=prov_token)
results.append(check("Rapor Kerja Kabupaten", c, d))
assert "data" in d
print(f"       Kabupaten aktif: {d.get('total_kabupaten_aktif')}")
print(f"       Rapor merah: {d.get('kabupaten_rapor_merah')}")
print(f"       Paling lambat: {d.get('kabupaten_terlambat')}")

# Cek masyarakat tidak bisa akses rapor kabupaten
c, d = req("GET", "/api/v1/admin/dashboard/rapor-kabupaten", token=pub_token)
results.append(check("Publik diblokir dari rapor kabupaten (403)", c, d, 403))

# ─── Ekspor ───────────────────────────────────────────────────────
print("\n[8] Ekspor Data")
r = urllib.request.Request(BASE + "/api/v1/admin/export.csv",
    headers={"Authorization": f"Bearer {prov_token}"})
try:
    res = urllib.request.urlopen(r)
    content = res.read().decode("utf-8")
    rows = content.strip().split("\n")
    results.append(check("Ekspor CSV", 200, {}))
    print(f"       CSV: {len(rows)} baris (termasuk header)")
except Exception as e:
    results.append(False)
    print(f"  {FAIL} Ekspor CSV gagal: {e}")

r = urllib.request.Request(BASE + "/api/v1/admin/export.xlsx",
    headers={"Authorization": f"Bearer {prov_token}"})
try:
    res = urllib.request.urlopen(r)
    raw = res.read()
    results.append(check("Ekspor Excel (.xlsx)", 200, {}))
    print(f"       XLSX: {len(raw):,} bytes")
except Exception as e:
    results.append(False)
    print(f"  {FAIL} Ekspor XLSX gagal: {e}")

# ─── Nonaktifkan petugas ──────────────────────────────────────────
print("\n[9] Manajemen Akun")
c, d = req("PATCH", f"/api/v1/admin/officers/{officer_id}/active?active=false", token=prov_token)
results.append(check("Nonaktifkan petugas Pemda", c, d))
assert d.get("is_active") == False

# Login dengan akun nonaktif harus gagal
c, d = req("POST", "/api/v1/auth/login/admin-pemda", {"identity": "198501012010010001", "password": "garut123"})
results.append(check("Login akun nonaktif ditolak (401)", c, d, 401))

# ─── Akses lintas wilayah (security check) ───────────────────────
print("\n[10] Security: Isolasi Wilayah")
# Seed a verified Bogor user; public registration requires email verification.
db = SessionLocal()
db.add(UserModel(
    nik="3201998877665544",
    email="bogor@test.com",
    full_name="User Bogor",
    password_hash=hash_password("bogor1234"),
    kode_kabupaten=3201,
    is_active=True,
    email_verified=True,
))
db.commit()
db.close()
c, d = req("POST", "/api/v1/auth/login", {"identity": "bogor@test.com", "password": "bogor1234"})
bogor_token = d.get("access_token")

# Buat laporan dari Bogor
c, d = form_req("/api/v1/reports", {
    "pelapor_nama": "User Bogor", "pelapor_nik": "3201998877665544",
    "pelapor_telepon": "081234", "pelapor_email": "bogor@test.com",
    "pelapor_domisili": "Kabupaten Bogor", "hubungan_pelapor": "Langsung",
    "usia_perempuan": "16", "usia_laki_laki": "19",
    "status_pendidikan": "SMA", "lokasi_kabupaten": "Kab Bogor",
    "lokasi_kecamatan_desa": "Cibinong", "waktu_rencana_akad": "01/01/2025",
    "faktor_pendorong": "Ekonomi",
    "description": "Laporan dari wilayah Bogor untuk tes isolasi wilayah.",
    "pernyataan_benar": "true", "setuju_pemrosesan": "true",
}, token=bogor_token)
bogor_report_id = d.get("id")

# Aktifkan kembali Garut untuk tes ini
c, _ = req("PATCH", f"/api/v1/admin/officers/{officer_id}/active?active=true", token=prov_token)
c, d = req("POST", "/api/v1/auth/login/admin-pemda", {"identity": "198501012010010001", "password": "garut123"})
pemda_token = d.get("access_token")

# Admin Garut coba akses laporan Bogor → harus 403
c, d = req("GET", f"/api/v1/reports/{bogor_report_id}", token=pemda_token)
results.append(check("Admin Garut diblokir akses laporan Bogor (403)", c, d, 403))

# ─── Statistik Publik ─────────────────────────────────────────────
print("\n[11] Statistik Publik")
c, d = req("GET", "/api/v1/statistik/pernikahan-dini")
results.append(check("GET /statistik/pernikahan-dini", c, d))
c, d = req("GET", "/api/v1/statistik/ringkasan")
results.append(check("GET /statistik/ringkasan", c, d))
c, d = req("GET", "/api/v1/statistik/putus-sekolah")
results.append(check("GET /statistik/putus-sekolah", c, d))

# ─── Hasil ───────────────────────────────────────────────────────
total = len(results)
passed = sum(results)
failed = total - passed
print(f"\n{'='*60}")
print(f"  Hasil: {passed}/{total} test passed", end="")
if failed > 0:
    print(f"  ({failed} GAGAL ⚠️)")
else:
    print("  — Semua test LULUS ✓")
print("="*60 + "\n")
if failed:
    sys.exit(1)
