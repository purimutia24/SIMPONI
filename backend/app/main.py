import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from sqlalchemy import inspect, select, text

from app.database import Base, SessionLocal, engine
from app.models import User
from app.routers import admin, auth, reports, statistik
from app.security import hash_password

app = FastAPI(
    title="API Sistem Pelaporan Pernikahan Dini",
    description="Backend melayani sistem pelaporan dan pemetaan kasus di Jawa Barat",
    version="1.0.0"
)

# Konfigurasi CORS agar bisa diakses oleh Frontend (React)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Untuk pengembangan lokal, izinkan semua origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Menyambungkan router statistik
app.include_router(statistik.router, prefix="/api/v1/statistik", tags=["Statistik"])
app.include_router(auth.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.on_event("startup")
def initialize_database():
    Base.metadata.create_all(bind=engine)
    user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
    with engine.begin() as connection:
        if "reset_token" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN reset_token VARCHAR(255)"))
        if "reset_expires_at" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN reset_expires_at DATETIME"))
    db = SessionLocal()
    try:
        nip = os.getenv("ADMIN_PROVINSI_NIP")
        password = os.getenv("ADMIN_PROVINSI_PASSWORD")
        if nip and password and not db.scalar(select(User).where(User.nik == nip)):
            db.add(User(nik=nip, email=os.getenv("ADMIN_PROVINSI_EMAIL", "admin@simponi.local"), full_name="Admin Pemprov", password_hash=hash_password(password), role="admin_pemprov"))
            db.commit()
    finally:
        db.close()

@app.get("/")
def read_root():
    return {
        "status": "success",
        "message": "Server FastAPI Backend Berjalan Normal!"
    }