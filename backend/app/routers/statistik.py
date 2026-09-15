from fastapi import APIRouter, HTTPException
import json
import os
from typing import List
from app.schemas import PutusSekolahResponse

router = APIRouter()

# Path file JSON hasil konversi lokal
PATH_PERNIKAHAN = "app/data/pernikahan_dini.json"
PATH_PUTUS_SEKOLAH = "app/data/putus_sekolah.json"

@router.get("/pernikahan-dini")
def get_pernikahan_dini():
    if not os.path.exists(PATH_PERNIKAHAN):
        raise HTTPException(status_code=404, detail="Data pernikahan dini belum dikonversi.")
    with open(PATH_PERNIKAHAN, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"status": "success", "data": data}

@router.get("/putus-sekolah", response_model=List[PutusSekolahResponse])
def get_putus_sekolah():
    if not os.path.exists(PATH_PUTUS_SEKOLAH):
        raise HTTPException(status_code=404, detail="Data putus sekolah belum dikonversi.")
    with open(PATH_PUTUS_SEKOLAH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data