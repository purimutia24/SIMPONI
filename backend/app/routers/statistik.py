from fastapi import APIRouter, HTTPException, Query
import json
import os
from copy import deepcopy
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PATH_PERNIKAHAN = DATA_DIR / "pernikahan_dini.json"
PATH_PUTUS_SEKOLAH = DATA_DIR / "putus_sekolah.json"
PATH_STUNTING = DATA_DIR / "stunting.json"
PATH_KEMISKINAN = DATA_DIR / "kemiskinan.json"
PATH_GEOJSON = DATA_DIR / "Jabar_By_Kab.geojson"
BPS_API_KEY = os.getenv("BPS_API_KEY")
BPS_BASE_URL = os.getenv("BPS_BASE_URL", "https://webapi.bps.go.id/v1/api")
BPS_STUNTING_URL = os.getenv("BPS_STUNTING_URL")
BPS_KEMISKINAN_URL = os.getenv("BPS_KEMISKINAN_URL")
BPS_DOMAIN = os.getenv("BPS_DOMAIN", "3200")
BPS_STUNTING_VAR = os.getenv("BPS_STUNTING_VAR")
BPS_KEMISKINAN_VAR = os.getenv("BPS_KEMISKINAN_VAR")


@lru_cache(maxsize=16)
def _load_json_file(path_string: str):
    path = Path(path_string)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File data belum tersedia: {path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail=f"Gagal membaca {path.name}: {error}") from error


def load_json_file(path: Path):
    return deepcopy(_load_json_file(str(path)))


def fetch_bps(indicator: str, configured_url: str | None, variable: str | None):
    if not BPS_API_KEY:
        raise HTTPException(status_code=503, detail="BPS_API_KEY belum dikonfigurasi")
    url = configured_url
    if not url:
        if not variable:
            raise HTTPException(
                status_code=503,
                detail=f"URL atau variabel BPS untuk {indicator} belum dikonfigurasi. Isi BPS_{indicator.upper()}_URL atau BPS_{indicator.upper()}_VAR.",
            )
        url = f"{BPS_BASE_URL}/list/model/data/lang/ind/domain/{quote(BPS_DOMAIN)}/var/{quote(variable)}/key/{quote(BPS_API_KEY)}/"
    elif "{api_key}" in url:
        url = url.format(api_key=quote(BPS_API_KEY))
    try:
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "SIMPONI/1.0"})
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise HTTPException(status_code=502, detail=f"BPS menolak permintaan {indicator}: HTTP {error.code}") from error
    except (URLError, TimeoutError, ValueError) as error:
        raise HTTPException(status_code=502, detail=f"Gagal mengambil data {indicator} dari BPS: {error}") from error
    if isinstance(payload, dict) and payload.get("status") not in (None, 200, "OK", "success"):
        raise HTTPException(status_code=502, detail=f"BPS mengembalikan status tidak berhasil untuk {indicator}: {payload.get('message', payload.get('status'))}")
    return {"status": "success", "source": "BPS API", "indicator": indicator, "data": payload}

@router.get("/pernikahan-dini")
def get_pernikahan_dini():
    return {"status": "success", "data": load_json_file(PATH_PERNIKAHAN)}

@router.get("/putus-sekolah")
def get_putus_sekolah():
    return {"status": "success", "data": load_json_file(PATH_PUTUS_SEKOLAH)}


@router.get("/peta-pernikahan-dini")
def get_peta_pernikahan_dini(tahun: int | None = Query(default=None, ge=2000, le=2100)):
    geojson = load_json_file(PATH_GEOJSON)
    rows = load_json_file(PATH_PERNIKAHAN)
    totals = {}
    years = {}
    for row in rows:
        if tahun is not None and row.get("tahun") != tahun:
            continue
        kode = row.get("kode_kabupaten_kota")
        if kode is None:
            continue
        kode = int(kode)
        totals[kode] = totals.get(kode, 0) + float(row.get("jumlah_perkawinan", 0) or 0)
        years[kode] = max(years.get(kode, 0), int(row.get("tahun", 0) or 0))

    maximum = max(totals.values(), default=0)
    for feature in geojson.get("features", []):
        properties = feature.setdefault("properties", {})
        kode = int(properties.get("ID_KAB", 0))
        value = totals.get(kode, 0)
        ratio = value / maximum if maximum else 0
        properties.update({
            "kode_kabupaten": kode,
            "nama_kabupaten": properties.get("KABKOT", ""),
            "jumlah_kasus": round(value, 2),
            "tahun": tahun or years.get(kode),
            "indikator": "pernikahan_dini",
            "tingkat_risiko": "tinggi" if ratio >= 0.66 else "sedang" if ratio >= 0.33 else "rendah",
        })
    return {"type": "FeatureCollection", "features": geojson.get("features", [])}


@router.get("/ringkasan")
def get_ringkasan():
    if not PATH_PERNIKAHAN.exists():
        raise HTTPException(status_code=404, detail="Data statistik belum tersedia")
    try:
        data = load_json_file(PATH_PERNIKAHAN)
        by_year = {}
        by_region = {}
        for row in data:
            year = str(row.get("tahun", "Tidak diketahui"))
            region = row.get("nama_kabupaten_kota", "Tidak diketahui")
            value = float(row.get("jumlah_perkawinan", 0) or 0)
            by_year[year] = by_year.get(year, 0) + value
            by_region[region] = by_region.get(region, 0) + value
        return {"status": "success", "total": sum(by_year.values()), "by_year": by_year, "by_region": by_region}
    except (OSError, ValueError, TypeError) as error:
        raise HTTPException(status_code=500, detail=f"Gagal mengolah statistik: {error}") from error

@router.get("/stunting")
def get_stunting():
    return {"status": "success", "source": "excel", "data": load_json_file(PATH_STUNTING)}


@router.get("/stunting-lokal")
def get_stunting_lokal():
    return {"status": "success", "source": "file", "data": load_json_file(PATH_STUNTING)}

@router.get("/kemiskinan")
def get_kemiskinan():
    return {"status": "success", "source": "excel", "data": load_json_file(PATH_KEMISKINAN)}


@router.get("/kemiskinan-lokal")
def get_kemiskinan_lokal():
    return {"status": "success", "source": "file", "data": load_json_file(PATH_KEMISKINAN)}


@router.get("/stunting-bps")
def get_stunting_bps():
    if BPS_STUNTING_URL or BPS_STUNTING_VAR:
        return fetch_bps("stunting", BPS_STUNTING_URL, BPS_STUNTING_VAR)
    return {
        "status": "success",
        "source": "excel-fallback",
        "message": "Konfigurasi BPS belum diisi; data dikembalikan dari Data_Stunting.xlsx.",
        "data": load_json_file(PATH_STUNTING),
    }


@router.get("/kemiskinan-bps")
def get_kemiskinan_bps():
    if BPS_KEMISKINAN_URL or BPS_KEMISKINAN_VAR:
        return fetch_bps("kemiskinan", BPS_KEMISKINAN_URL, BPS_KEMISKINAN_VAR)
    return {
        "status": "success",
        "source": "excel-fallback",
        "message": "Konfigurasi BPS belum diisi; data dikembalikan dari Data_Kemiskinan.xlsx.",
        "data": load_json_file(PATH_KEMISKINAN),
    }