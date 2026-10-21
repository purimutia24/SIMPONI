from datetime import datetime
from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

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
    identity: str = Field(
        min_length=3,
        validation_alias=AliasChoices("identity", "identifier"),
    )
    password: str = Field(min_length=1)

    @field_validator("identity")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        return value.strip().lower()


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Email tidak valid")
        return value


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("token")
    @classmethod
    def validate_reset_token(cls, value: str) -> str:
        value = value.strip().strip('"')
        if len(value) < 20:
            raise ValueError("Token harus diambil dari tautan pemulihan yang dikirim melalui email")
        return value


class VerificationResponse(BaseModel):
    status: str
    message: str


class UserResponse(BaseModel):
    id: int
    nik: Optional[str] = None
    nip: Optional[str] = None
    email: str
    full_name: str
    role: str
    kode_kabupaten: Optional[int] = None
    is_active: bool
    email_verified: bool

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ReportCreate(BaseModel):
    pelapor_nama: str = Field(max_length=150)
    pelapor_nik: str = Field(min_length=16, max_length=16)
    pelapor_telepon: str = Field(max_length=20)
    pelapor_email: str = Field(max_length=255)
    pelapor_domisili: str = Field(max_length=150)
    hubungan_pelapor: str = Field(max_length=100)
    usia_perempuan: str = Field(max_length=50)
    usia_laki_laki: str = Field(max_length=50)
    status_pendidikan: str = Field(max_length=100)
    lokasi_kabupaten: str = Field(max_length=150)
    lokasi_kecamatan_desa: str = Field(max_length=255)
    waktu_rencana_akad: str = Field(max_length=100)
    faktor_pendorong: str = Field(max_length=255)
    description: str = Field(min_length=10, max_length=10000)
    pernyataan_benar: bool
    setuju_pemrosesan: bool


ReportStatus = Literal["Diajukan", "Diverifikasi", "Diproses", "Selesai", "Ditolak"]


class ReportUpdate(BaseModel):
    status: ReportStatus
    note: str = Field(min_length=3, max_length=5000)


class DispositionCreate(BaseModel):
    tujuan: str = Field(min_length=2, max_length=150)
    catatan: str = Field(min_length=3, max_length=5000)


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
    pelapor_nama: str
    pelapor_nik: str
    pelapor_telepon: str
    pelapor_email: str
    pelapor_domisili: str
    hubungan_pelapor: str
    usia_perempuan: str
    usia_laki_laki: str
    status_pendidikan: str
    lokasi_kabupaten: str
    lokasi_kecamatan_desa: str
    waktu_rencana_akad: str
    faktor_pendorong: str
    description: str
    dokumen_pendukung: Optional[str]
    foto_bukti_awal: Optional[str] = None
    pernyataan_benar: bool
    setuju_pemrosesan: bool
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


class OfficerUpdate(BaseModel):
    nip: str | None = Field(default=None, min_length=8, max_length=30)
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    kode_kabupaten: int | None = Field(default=None, ge=3201, le=3279)

    @field_validator("nip")
    @classmethod
    def normalize_officer_nip(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value.isdigit():
            raise ValueError("NIP harus berupa angka")
        return value

    @field_validator("full_name")
    @classmethod
    def normalize_officer_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Nama petugas minimal 2 karakter")
        return value

    @field_validator("email")
    @classmethod
    def normalize_officer_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Email tidak valid")
        return value

    @model_validator(mode="after")
    def require_update_field(self):
        if not self.model_fields_set or (
            self.model_fields_set == {"password"} and self.password is None
        ):
            raise ValueError("Minimal satu data petugas harus diisi")
        if any(
            getattr(self, field) is None
            for field in self.model_fields_set
            if field != "password"
        ):
            raise ValueError("Data petugas tidak boleh bernilai null")
        return self


class ProvincialAdminCreate(BaseModel):
    nip: str = Field(min_length=8, max_length=30)
    full_name: str = Field(min_length=2, max_length=150)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_admin_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Email tidak valid")
        return value

    @field_validator("nip")
    @classmethod
    def normalize_nip(cls, value: str) -> str:
        value = value.strip()
        if not value.isdigit():
            raise ValueError("NIP harus berupa angka")
        return value


class StatisticUpdate(BaseModel):
    tahun: int = Field(ge=2000, le=2100)
    kode_kabupaten_kota: int = Field(ge=3201, le=3279)
    nama_kabupaten_kota: str
    jumlah_perkawinan: float = Field(ge=0)
    jenis_kelamin: Optional[str] = None