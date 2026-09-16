import csv
import io
import json
from datetime import date, datetime, time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models import Report, User
from app.schemas import OfficerCreate, StatisticUpdate, UserResponse
from app.security import hash_password

router = APIRouter(prefix="/admin", tags=["Administrasi"])
STATISTIC_FILE = Path(__file__).resolve().parents[1] / "data" / "pernikahan_dini.json"


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(require_roles("admin_pemda", "admin_pemprov"))):
    base = select(Report)
    if user.role == "admin_pemda":
        base = base.where(Report.kode_kabupaten == user.kode_kabupaten)
    rows = db.scalars(base).all()
    counts = {status: sum(report.status == status for report in rows) for status in ["Diajukan", "Diverifikasi", "Diproses", "Selesai", "Ditolak"]}
    return {"scope": user.kode_kabupaten if user.role == "admin_pemda" else "Jawa Barat", "total": len(rows), "by_status": counts, "queue": counts["Diajukan"] + counts["Diverifikasi"]}


@router.post("/officers", response_model=UserResponse, status_code=201)
def create_officer(payload: OfficerCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin_pemprov"))):
    if db.scalar(select(User).where((User.nik == payload.nip) | (User.email == payload.email))):
        raise HTTPException(status_code=409, detail="NIP atau email sudah digunakan")
    officer = User(
        nik=payload.nip,
        email=payload.email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role="admin_pemda",
        kode_kabupaten=payload.kode_kabupaten,
    )
    db.add(officer)
    db.commit()
    db.refresh(officer)
    return officer


@router.patch("/officers/{officer_id}/active", response_model=UserResponse)
def set_officer_active(officer_id: int, active: bool = Query(...), db: Session = Depends(get_db), user: User = Depends(require_roles("admin_pemprov"))):
    officer = db.get(User, officer_id)
    if not officer or officer.role != "admin_pemda":
        raise HTTPException(status_code=404, detail="Petugas tidak ditemukan")
    officer.is_active = active
    db.commit()
    db.refresh(officer)
    return officer


@router.get("/officers", response_model=list[UserResponse])
def list_officers(db: Session = Depends(get_db), user: User = Depends(require_roles("admin_pemprov"))):
    return db.scalars(select(User).where(User.role == "admin_pemda").order_by(User.full_name)).all()


@router.post("/statistics", status_code=201)
def upsert_statistic(payload: StatisticUpdate, user: User = Depends(require_roles("admin_pemprov"))):
    data = json.loads(STATISTIC_FILE.read_text(encoding="utf-8")) if STATISTIC_FILE.exists() else []
    item = payload.model_dump()
    item["id"] = max((row.get("id", 0) for row in data), default=0) + 1
    for index, row in enumerate(data):
        if row.get("tahun") == payload.tahun and row.get("kode_kabupaten_kota") == payload.kode_kabupaten_kota and row.get("jenis_kelamin") == payload.jenis_kelamin:
            item["id"] = row.get("id", item["id"])
            data[index] = item
            break
    else:
        data.append(item)
    STATISTIC_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "success", "data": item}


@router.get("/export.csv")
def export_reports(
    start_date: date | None = None,
    end_date: date | None = None,
    kode_kabupaten: int | None = Query(default=None, ge=3201, le=3279),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemda", "admin_pemprov")),
):
    query = select(Report, User).join(User, User.id == Report.reporter_id).order_by(Report.created_at)
    if user.role == "admin_pemda":
        query = query.where(Report.kode_kabupaten == user.kode_kabupaten)
    elif kode_kabupaten:
        query = query.where(Report.kode_kabupaten == kode_kabupaten)
    if start_date:
        query = query.where(Report.created_at >= datetime.combine(start_date, time.min))
    if end_date:
        query = query.where(Report.created_at <= datetime.combine(end_date, time.max))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "pelapor", "email", "kode_kabupaten", "deskripsi", "status", "dibuat", "diperbarui"])
    for report, reporter in db.execute(query):
        writer.writerow([report.id, reporter.full_name, reporter.email, report.kode_kabupaten, report.description, report.status, report.created_at.isoformat(), report.updated_at.isoformat()])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=rekap-laporan.csv"})
