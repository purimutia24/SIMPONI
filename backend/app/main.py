from fastapi import FastAPI

app = FastAPI(
    title="API Sistem Pelaporan Pernikahan Dini",
    description="Backend melayani sistem pelaporan dan pemetaan kasus di Jawa Barat",
    version="1.0.0"
)

# Endpoint dasar untuk mengecek status server (Health Check)
@app.get("/")
def read_root():
    return {
        "status": "success",
        "message": "Server FastAPI Backend Berjalan Normal!"
    }