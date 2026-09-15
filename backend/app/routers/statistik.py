from fastapi import APIRouter, HTTPException
import json
import os
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()

PATH_PERNIKAHAN = "app/data/pernikahan_dini.json"
PATH_PUTUS_SEKOLAH = "app/data/putus_sekolah.json"
BPS_API_KEY = os.getenv("BPS_API_KEY")

@router.get("/pernikahan-dini")
def get_pernikahan_dini():
    if not os.path.exists(PATH_PERNIKAHAN):
        raise HTTPException(status_code=404, detail="File JSON pernikahan dini belum tersedia. Jalankan convert.py terlebih dahulu.")
    try:
        with open(PATH_PERNIKAHAN, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal membaca data: {str(e)}")

@router.get("/putus-sekolah")
def get_putus_sekolah():
    if not os.path.exists(PATH_PUTUS_SEKOLAH):
        raise HTTPException(status_code=404, detail="File JSON putus sekolah belum tersedia.")
    try:
        with open(PATH_PUTUS_SEKOLAH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal membaca data: {str(e)}")

@router.get("/stunting")
async def get_stunting():
    if not BPS_API_KEY:
        return {"status": "warning", "message": "BPS_API_KEY belum dikonfigurasi di file .env"}
    return {"status": "success", "source": "BPS API", "data": "Endpoint stunting aktif."}

@router.get("/kemiskinan")
async def get_kemiskinan():
    if not BPS_API_KEY:
        return {"status": "warning", "message": "BPS_API_KEY belum dikonfigurasi di file .env"}
    return {"status": "success", "source": "BPS API", "data": "Endpoint kemiskinan aktif."}