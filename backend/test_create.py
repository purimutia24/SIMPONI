import urllib.request
import urllib.parse
import json

url = "http://127.0.0.1:8000/api/v1/auth/register"
req = urllib.request.Request(url, data=json.dumps({
    "nik": "3201123456789012",
    "email": "test@example.com",
    "full_name": "Test User",
    "password": "password123"
}).encode(), headers={'Content-Type': 'application/json'})

res = urllib.request.urlopen(req)
data = json.loads(res.read())
print("Register:", data)
token = data.get("access_token")

url = "http://127.0.0.1:8000/api/v1/reports"
data = {
    "pelapor_nama": "Rahmat Hidayat",
    "pelapor_nik": "3201123456789012",
    "pelapor_telepon": "083812345678",
    "pelapor_email": "rahmathidayat@gmail.com",
    "pelapor_domisili": "Kabupaten Bogor",
    "hubungan_pelapor": "Calon mempelai perempuan",
    "usia_perempuan": "15 Tahun",
    "usia_laki_laki": "17 Tahun",
    "status_pendidikan": "Putus Sekolah (SD)",
    "lokasi_kabupaten": "Kabupaten Bogor",
    "lokasi_kecamatan_desa": "Kecamatan Cibinong, Desa Tegar",
    "waktu_rencana_akad": "10/10/2024",
    "faktor_pendorong": "Tekanan / Paksaan Orang Tua",
    "description": "Kronologi...",
    "pernyataan_benar": "true",
    "setuju_pemrosesan": "true"
}

from urllib.parse import urlencode
encoded_data = urlencode(data).encode('utf-8')
req = urllib.request.Request(url, data=encoded_data, headers={
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/x-www-form-urlencoded'
})
try:
    res = urllib.request.urlopen(req)
    print("Create Report:", json.loads(res.read()))
except Exception as e:
    print(e)
    print(e.read().decode())
