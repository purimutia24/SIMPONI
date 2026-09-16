from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Skema untuk Data Pernikahan Dini (menyesuaikan kolom Excel)
class PernikahanDiniResponse(BaseModel):
    # Sesuaikan atribut di bawah ini dengan nama kolom asli di file JSON/Excel-mu
    kabupaten_kota: Optional[str] = None
    jumlah_kasus: Optional[int] = 0
    tahun: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

# Skema untuk Data Putus Sekolah (berdasarkan konversi loop kita sebelumnya)
class PutusSekolahResponse(BaseModel):
    nama_kabupaten_kota: str
    putus_sd: int
    putus_smp: int
    putus_sma: int
    putus_smk: int

    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    nik: str = Field(min_length=16, max_length=16, pattern=r"^\d{16}$")
    email: str
    full_name: str = Field(min_length=2, max_length=150)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Email tidak valid")
        return value.lower()


class LoginRequest(BaseModel):
    identity: str = Field(min_length=3)
    password: str = Field(min_length=1)


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("token")
    @classmethod
    def validate_reset_token(cls, value: str) -> str:
        value = value.strip().strip('"')
        if len(value) < 20:
            raise ValueError("Token harus diambil dari response forgot-password")
        return value


class UserResponse(BaseModel):
    id: int
    nik: Optional[str] = None
    email: str
    full_name: str
    role: str
    kode_kabupaten: Optional[int] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ReportCreate(BaseModel):
    description: str = Field(min_length=10, max_length=10000)


ReportStatus = Literal["Diajukan", "Diverifikasi", "Diproses", "Selesai", "Ditolak"]


class ReportUpdate(BaseModel):
    status: ReportStatus
    note: str = Field(min_length=3, max_length=5000)
    assigned_kode_kabupaten: Optional[int] = Field(default=None, ge=3201, le=3279)


class HistoryResponse(BaseModel):
    id: int
    actor_id: Optional[int]
    old_status: Optional[str]
    new_status: str
    note: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportResponse(BaseModel):
    id: int
    reporter_id: int
    kode_kabupaten: int
    description: str
    status: str
    created_at: datetime
    updated_at: datetime
    histories: list[HistoryResponse] = []

    model_config = ConfigDict(from_attributes=True)


class OfficerCreate(BaseModel):
    nip: str = Field(min_length=8, max_length=30)
    full_name: str = Field(min_length=2, max_length=150)
    email: str
    password: str = Field(min_length=8, max_length=128)
    kode_kabupaten: int = Field(ge=3201, le=3279)


class StatisticUpdate(BaseModel):
    tahun: int = Field(ge=2000, le=2100)
    kode_kabupaten_kota: int = Field(ge=3201, le=3279)
    nama_kabupaten_kota: str
    jumlah_perkawinan: float = Field(ge=0)
    jenis_kelamin: Optional[str] = None