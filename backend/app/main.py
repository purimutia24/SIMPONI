import mimetypes
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.middleware.gzip import GZipMiddleware
from sqlalchemy import inspect, select, text
from pathlib import Path

from app.database import Base, SessionLocal, engine
from app.models import User
import app.models
from app.routers import admin, auth, reports, statistik
from app.security import hash_password

app = FastAPI(
    title="SIMPONI — Sistem Pelaporan Pernikahan Dini",
    description=(
        "Backend API untuk sistem pelaporan, pemetaan, dan penanganan kasus "
        "pernikahan dini di Jawa Barat. Melayani Masyarakat, Admin Pemda, dan Admin Pemprov."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── Middleware ────────────────────────────────────────────────────────────────

default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
configured_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]
frontend_origins = list(dict.fromkeys(default_origins + configured_origins))

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Upload directory ─────────────────────────────────────────────────────────
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def ensure_report_photo_column(database_engine=engine):
    report_columns = {
        column["name"] for column in inspect(database_engine).get_columns("reports")
    }
    if "foto_bukti_awal" not in report_columns:
        with database_engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE reports ADD COLUMN foto_bukti_awal VARCHAR(255)"
            ))


# ─── Router ───────────────────────────────────────────────────────────────────
app.include_router(statistik.router, prefix="/api/v1/statistik", tags=["Statistik Publik"])
app.include_router(auth.router,      prefix="/api/v1",           tags=["Autentikasi"])
app.include_router(reports.router,   prefix="/api/v1",           tags=["Laporan"])
app.include_router(admin.router,     prefix="/api/v1",           tags=["Administrasi"])


# ─── Startup ──────────────────────────────────────────────────────────────────
@app.on_event("startup")
def initialize_database():
    """Buat semua tabel (idempoten) dan seed akun Admin Pemprov jika belum ada."""
    Base.metadata.create_all(bind=engine)
    ensure_report_photo_column()

    # Migrasi kolom lama jika menggunakan DB yang sudah ada sebelum skema baru
    if engine.dialect.name == "sqlite":
        try:
            existing_cols = {c["name"] for c in inspect(engine).get_columns("users")}
            with engine.begin() as conn:
                if "reset_token" not in existing_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN reset_token VARCHAR(255)"))
                if "reset_expires_at" not in existing_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN reset_expires_at DATETIME"))
                if "email_verified" not in existing_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 1"))
                if "verification_token" not in existing_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN verification_token VARCHAR(64)"))
                if "verification_expires_at" not in existing_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN verification_expires_at DATETIME"))
                if "nip" not in existing_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN nip VARCHAR(30)"))
                conn.execute(text(
                    "UPDATE users SET nip = nik, nik = NULL "
                    "WHERE role IN ('admin_pemda', 'admin_pemprov') "
                    "AND nip IS NULL AND nik IS NOT NULL"
                ))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_nip ON users (nip)"))
        except Exception:
            pass  # Tabel mungkin belum ada sama sekali (sudah di-create_all)
    else:
        existing_cols = {column["name"] for column in inspect(engine).get_columns("users")}
        column_definitions = {
            "nip": "VARCHAR(30) NULL",
            "email_verified": "BOOLEAN NOT NULL DEFAULT TRUE",
            "verification_token": "VARCHAR(64) NULL",
            "verification_expires_at": "DATETIME NULL",
        }
        missing = {
            name: definition
            for name, definition in column_definitions.items()
            if name not in existing_cols
        }
        if missing:
            with engine.begin() as conn:
                for name, definition in missing.items():
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {definition}"))
        if engine.dialect.name == "mysql":
            nik_column = next(
                column for column in inspect(engine).get_columns("users")
                if column["name"] == "nik"
            )
            if not nik_column["nullable"]:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE users MODIFY nik VARCHAR(20) NULL"))
        elif engine.dialect.name == "postgresql":
            nik_column = next(
                column for column in inspect(engine).get_columns("users")
                if column["name"] == "nik"
            )
            if not nik_column["nullable"]:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE users ALTER COLUMN nik DROP NOT NULL"))
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE users SET nip = nik, nik = NULL "
                "WHERE role IN ('admin_pemda', 'admin_pemprov') "
                "AND nip IS NULL AND nik IS NOT NULL"
            ))
        existing_indexes = {index["name"] for index in inspect(engine).get_indexes("users")}
        if "ix_users_nip" not in existing_indexes:
            with engine.begin() as conn:
                conn.execute(text("CREATE UNIQUE INDEX ix_users_nip ON users (nip)"))

    if engine.dialect.name == "mysql" and "report_histories" in inspect(engine).get_table_names():
        history_fks = inspect(engine).get_foreign_keys("report_histories")
        report_fk = next((
            foreign_key for foreign_key in history_fks
            if foreign_key.get("constrained_columns") == ["report_id"]
        ), None)
        if not report_fk or report_fk.get("referred_table") != "reports":
            with engine.connect() as conn:
                history_count = conn.execute(text("SELECT COUNT(*) FROM report_histories")).scalar_one()
                report_id_type = conn.execute(text(
                    "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() "
                    "AND TABLE_NAME = 'report_histories' AND COLUMN_NAME = 'report_id'"
                )).scalar_one()
                orphan_count = conn.execute(text(
                    "SELECT COUNT(*) FROM report_histories AS history "
                    "LEFT JOIN reports AS report ON report.id = history.report_id "
                    "WHERE report.id IS NULL"
                )).scalar_one()
            if history_count and report_id_type.lower() not in {"int", "int unsigned"}:
                raise RuntimeError(
                    "Migrasi report_histories memerlukan pemetaan data lama: "
                    f"report_id bertipe {report_id_type} dan ada {history_count} riwayat"
                )
            if orphan_count:
                raise RuntimeError(
                    "Migrasi foreign key report_histories dibatalkan: "
                    f"ada {orphan_count} riwayat tanpa pasangan di tabel reports"
                )
            with engine.begin() as conn:
                if report_fk:
                    constraint_name = report_fk.get("name")
                    if not constraint_name or not constraint_name.replace("_", "").isalnum():
                        raise RuntimeError("Nama foreign key report_histories tidak valid untuk migrasi")
                    conn.execute(text(
                        f"ALTER TABLE report_histories DROP FOREIGN KEY `{constraint_name}`"
                    ))
                if report_id_type.lower() not in {"int", "int unsigned"}:
                    conn.execute(text(
                        "ALTER TABLE report_histories MODIFY report_id INT NOT NULL"
                    ))
                conn.execute(text(
                    "ALTER TABLE report_histories "
                    "ADD CONSTRAINT fk_report_histories_reports "
                    "FOREIGN KEY (report_id) REFERENCES reports (id)"
                ))

    # Seed akun Admin Pemprov dari environment variable
    nip      = os.getenv("ADMIN_PROVINSI_NIP")
    password = os.getenv("ADMIN_PROVINSI_PASSWORD")
    if nip and password:
        db = SessionLocal()
        try:
            if not db.scalar(select(User).where((User.nip == nip) | (User.email == os.getenv("ADMIN_PROVINSI_EMAIL", "admin@simponi.local")))):
                db.add(User(
                    nip=nip,
                    email=os.getenv("ADMIN_PROVINSI_EMAIL", "admin@simponi.local"),
                    full_name="Admin Pemprov Jawa Barat",
                    password_hash=hash_password(password),
                    role="admin_pemprov",
                    email_verified=True,
                ))
                db.commit()
        finally:
            db.close()


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def read_root():
    return {
        "status": "success",
        "app": "SIMPONI API v2.0",
        "message": "Server berjalan normal. Buka /docs untuk dokumentasi interaktif.",
    }


@app.get("/health", tags=["Health"])
def health_check():
    """Endpoint health check untuk monitoring uptime."""
    from sqlalchemy import text as sql_text
    try:
        with engine.connect() as conn:
            conn.execute(sql_text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"
    return {"status": "ok", "database": db_status}


# ─── Serve Upload Files ────────────────────────────────────────────────────────
@app.get("/uploads/{filename}", tags=["Dokumen"])
def serve_upload(filename: str):
    """Download / tampilkan dokumen pendukung yang diunggah pelapor."""
    if Path(filename).name != filename:
        raise HTTPException(status_code=404, detail="File tidak ditemukan")
    file_path = UPLOAD_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File tidak ditemukan")
    media_type, _ = mimetypes.guess_type(file_path.name)
    is_image = bool(media_type and media_type.startswith("image/"))
    return FileResponse(
        path=str(file_path),
        filename=None if is_image else filename,
        media_type=media_type,
        content_disposition_type="inline" if is_image else "attachment",
    )
