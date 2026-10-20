from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
	return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
	__tablename__ = "users"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	nik: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
	nip: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True, index=True)
	email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
	full_name: Mapped[str] = mapped_column(String(150))
	password_hash: Mapped[str] = mapped_column(String(255))
	role: Mapped[str] = mapped_column(String(30), default="public", index=True)
	kode_kabupaten: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
	is_active: Mapped[bool] = mapped_column(Boolean, default=True)
	email_verified: Mapped[bool] = mapped_column(Boolean, default=True)
	verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
	verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
	reset_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
	reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

	reports = relationship("Report", back_populates="reporter")


class AccessToken(Base):
	__tablename__ = "access_tokens"

	token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
	user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
	expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
	revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Report(Base):
	__tablename__ = "reports"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
	kode_kabupaten: Mapped[int] = mapped_column(Integer, index=True)
	pelapor_nama: Mapped[str] = mapped_column(String(150))
	pelapor_nik: Mapped[str] = mapped_column(String(16))
	pelapor_telepon: Mapped[str] = mapped_column(String(20))
	pelapor_email: Mapped[str] = mapped_column(String(255))
	pelapor_domisili: Mapped[str] = mapped_column(String(150))
	hubungan_pelapor: Mapped[str] = mapped_column(String(100))
	usia_perempuan: Mapped[str] = mapped_column(String(50))
	usia_laki_laki: Mapped[str] = mapped_column(String(50))
	status_pendidikan: Mapped[str] = mapped_column(String(100))
	lokasi_kabupaten: Mapped[str] = mapped_column(String(150))
	lokasi_kecamatan_desa: Mapped[str] = mapped_column(String(255))
	waktu_rencana_akad: Mapped[str] = mapped_column(String(100))
	faktor_pendorong: Mapped[str] = mapped_column(String(255))
	description: Mapped[str] = mapped_column(Text)
	foto_bukti_awal: Mapped[str | None] = mapped_column(String(255), nullable=True)
	dokumen_pendukung: Mapped[str | None] = mapped_column(String(255), nullable=True)
	pernyataan_benar: Mapped[bool] = mapped_column(Boolean, default=False)
	setuju_pemrosesan: Mapped[bool] = mapped_column(Boolean, default=False)
	status: Mapped[str] = mapped_column(String(20), default="Diajukan", index=True)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
	updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

	reporter = relationship("User", back_populates="reports")
	histories = relationship("ReportHistory", back_populates="report", cascade="all, delete-orphan")


class ReportHistory(Base):
	__tablename__ = "report_histories"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), index=True)
	actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
	old_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
	new_status: Mapped[str] = mapped_column(String(20))
	note: Mapped[str] = mapped_column(Text)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

	report = relationship("Report", back_populates="histories")
