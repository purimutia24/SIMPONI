from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
	__tablename__ = "users"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	nik: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True, index=True)
	email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
	full_name: Mapped[str] = mapped_column(String(150))
	password_hash: Mapped[str] = mapped_column(String(255))
	role: Mapped[str] = mapped_column(String(30), default="public", index=True)
	kode_kabupaten: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
	is_active: Mapped[bool] = mapped_column(Boolean, default=True)
	reset_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
	reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

	reports = relationship("Report", back_populates="reporter")


class Report(Base):
	__tablename__ = "reports"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
	kode_kabupaten: Mapped[int] = mapped_column(Integer, index=True)
	description: Mapped[str] = mapped_column(Text)
	status: Mapped[str] = mapped_column(String(20), default="Diajukan", index=True)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
	updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

	report = relationship("Report", back_populates="histories")
