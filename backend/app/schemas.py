from pydantic import BaseModel
from typing import Optional, List

# Skema untuk Data Pernikahan Dini (menyesuaikan kolom Excel)
class PernikahanDiniResponse(BaseModel):
    # Sesuaikan atribut di bawah ini dengan nama kolom asli di file JSON/Excel-mu
    kabupaten_kota: Optional[str] = None
    jumlah_kasus: Optional[int] = 0
    tahun: Optional[int] = None

    class Config:
        from_attributes = True

# Skema untuk Data Putus Sekolah (berdasarkan konversi loop kita sebelumnya)
class PutusSekolahResponse(BaseModel):
    nama_kabupaten_kota: str
    putus_sd: int
    putus_smp: int
    putus_sma: int
    putus_smk: int

    class Config:
        from_attributes = True