from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import statistik

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

# Menyambungkan router statistik
app.include_router(statistik.router, prefix="/api/v1/statistik", tags=["Statistik"])

@app.get("/")
def read_root():
    return {
        "status": "success",
        "message": "Server FastAPI Backend Berjalan Normal!"
    }