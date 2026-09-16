from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models import Report, ReportHistory, User
from app.schemas import ReportCreate, ReportResponse, ReportUpdate

router = APIRouter(prefix="/reports", tags=["Laporan"])


def load_report(db: Session, report_id: int) -> Report:
    report = db.scalar(
        select(Report).options(selectinload(Report.histories)).where(Report.id == report_id)
    )
    if not report:
        raise HTTPException(status_code=404, detail="Laporan tidak ditemukan")
    return report


@router.post("", response_model=ReportResponse, status_code=201)
def create_report(payload: ReportCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("public"))):
    if user.kode_kabupaten is None:
        raise HTTPException(status_code=422, detail="Akun belum memiliki kode kabupaten")
    report = Report(reporter_id=user.id, kode_kabupaten=user.kode_kabupaten, description=payload.description.strip())
    db.add(report)
    db.flush()
    db.add(ReportHistory(report_id=report.id, actor_id=user.id, new_status="Diajukan", note="Laporan dibuat oleh pelapor"))
    db.commit()
    return load_report(db, report.id)


@router.get("/mine", response_model=list[ReportResponse])
def my_reports(db: Session = Depends(get_db), user: User = Depends(require_roles("public"))):
    return db.scalars(
        select(Report).options(selectinload(Report.histories)).where(Report.reporter_id == user.id).order_by(Report.created_at.desc())
    ).all()


@router.get("/{report_id}", response_model=ReportResponse)
def report_detail(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = load_report(db, report_id)
    if user.role == "public" and report.reporter_id != user.id:
        raise HTTPException(status_code=403, detail="Laporan bukan milik Anda")
    if user.role == "admin_pemda" and report.kode_kabupaten != user.kode_kabupaten:
        raise HTTPException(status_code=403, detail="Laporan di luar wilayah tugas")
    return report


@router.get("", response_model=list[ReportResponse])
def list_reports(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemda", "admin_pemprov")),
):
    query = select(Report).options(selectinload(Report.histories)).order_by(Report.created_at.desc())
    if user.role == "admin_pemda":
        query = query.where(Report.kode_kabupaten == user.kode_kabupaten)
    return db.scalars(query).all()


@router.patch("/{report_id}", response_model=ReportResponse)
def update_report(
    report_id: int,
    payload: ReportUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemda")),
):
    report = load_report(db, report_id)
    if report.kode_kabupaten != user.kode_kabupaten:
        raise HTTPException(status_code=403, detail="Laporan di luar wilayah tugas")
    old_status = report.status
    report.status = payload.status
    report.updated_at = datetime.utcnow()
    if payload.assigned_kode_kabupaten is not None:
        report.kode_kabupaten = payload.assigned_kode_kabupaten
    db.add(ReportHistory(report_id=report.id, actor_id=user.id, old_status=old_status, new_status=payload.status, note=payload.note))
    db.commit()
    return load_report(db, report.id)
