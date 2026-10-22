import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models import Report, ReportHistory, User, utcnow
from app.report_scope import is_report_in_admin_scope, scope_reports_to_user
from app.schemas import DispositionCreate, ReportResponse, ReportUpdate

router = APIRouter(prefix="/reports", tags=["Laporan"])
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def load_report(db: Session, report_id: int) -> Report:
    report = db.scalar(
        select(Report).options(selectinload(Report.histories)).where(Report.id == report_id)
    )
    if not report:
        raise HTTPException(status_code=404, detail="Laporan tidak ditemukan")
    return report


def save_upload(upload: UploadFile | None) -> str | None:
    if not upload or not upload.filename:
        return None

    upload.file.seek(0)
    content = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Ukuran setiap file maksimal 2 MB",
        )

    UPLOAD_DIR.mkdir(exist_ok=True)
    extension = Path(upload.filename).suffix.lower()
    if extension and not extension[1:].isalnum():
        extension = ""
    unique_name = f"{uuid.uuid4().hex}{extension}"
    (UPLOAD_DIR / unique_name).write_bytes(content)
    return f"uploads/{unique_name}"


@router.post("", response_model=ReportResponse, status_code=201)
def create_report(
    pelapor_telepon: str = Form(...),
    pelapor_email: str = Form(...),
    pelapor_domisili: str = Form(...),
    hubungan_pelapor: str = Form(...),
    usia_perempuan: str = Form(...),
    usia_laki_laki: str = Form(...),
    status_pendidikan: str = Form(...),
    lokasi_kabupaten: str = Form(...),
    lokasi_kecamatan_desa: str = Form(...),
    waktu_rencana_akad: str = Form(...),
    faktor_pendorong: str = Form(...),
    description: str = Form(..., min_length=100, max_length=10000),
    pernyataan_benar: bool = Form(...),
    setuju_pemrosesan: bool = Form(...),
    foto_bukti_awal: UploadFile = File(None),
    foto_bukti: UploadFile = File(None),
    dokumen_pendukung_lain: UploadFile = File(None),
    dokumen_pendukung: UploadFile = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("public"))
):
    if user.kode_kabupaten is None:
        raise HTTPException(status_code=422, detail="Akun belum memiliki kode kabupaten")
    if not user.full_name.strip() or not user.nik or not user.nik.isdigit() or len(user.nik) != 16:
        raise HTTPException(
            status_code=422,
            detail="Profil akun belum memiliki nama dan NIK yang valid",
        )
    if len(description.strip()) < 100:
        raise HTTPException(
            status_code=422,
            detail="Kronologi wajib diisi minimal 100 karakter",
        )

    photo_upload = foto_bukti_awal or foto_bukti
    document_upload = dokumen_pendukung or dokumen_pendukung_lain
    if not any(
        upload and upload.filename
        for upload in (photo_upload, document_upload)
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "File bukti wajib diunggah dengan field foto_bukti_awal, "
                "foto_bukti, atau dokumen_pendukung"
            ),
        )

    for upload in (
        foto_bukti_awal,
        foto_bukti,
        dokumen_pendukung_lain,
        dokumen_pendukung,
    ):
        if upload and upload.filename:
            upload.file.seek(0, 2)
            size = upload.file.tell()
            upload.file.seek(0)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Ukuran setiap file maksimal 2 MB",
                )

    foto_bukti_awal_path = save_upload(photo_upload)
    dokumen_pendukung_path = save_upload(document_upload)

    report = Report(
        reporter_id=user.id, kode_kabupaten=user.kode_kabupaten, pelapor_nama=user.full_name.strip(),
        pelapor_nik=user.nik, pelapor_telepon=pelapor_telepon, pelapor_email=pelapor_email, pelapor_domisili=pelapor_domisili,
        hubungan_pelapor=hubungan_pelapor, usia_perempuan=usia_perempuan, usia_laki_laki=usia_laki_laki, status_pendidikan=status_pendidikan,
        lokasi_kabupaten=lokasi_kabupaten, lokasi_kecamatan_desa=lokasi_kecamatan_desa, waktu_rencana_akad=waktu_rencana_akad,
        faktor_pendorong=faktor_pendorong, description=description.strip(),
        foto_bukti_awal=foto_bukti_awal_path, dokumen_pendukung=dokumen_pendukung_path,
        pernyataan_benar=pernyataan_benar, setuju_pemrosesan=setuju_pemrosesan
    )
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
    if user.role == "admin_pemda" and not is_report_in_admin_scope(report, user):
        raise HTTPException(status_code=403, detail="Laporan di luar wilayah tugas")
    return report


@router.get("", response_model=list[ReportResponse])
def list_reports(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemda", "admin_pemprov")),
):
    query = select(Report).options(selectinload(Report.histories)).order_by(Report.created_at.desc())
    query = scope_reports_to_user(query, user)
    return db.scalars(query).all()


@router.patch("/{report_id}", response_model=ReportResponse)
def update_report(
    report_id: int,
    payload: ReportUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemda")),
):
    report = load_report(db, report_id)
    if not is_report_in_admin_scope(report, user):
        raise HTTPException(status_code=403, detail="Laporan di luar wilayah tugas")
    old_status = report.status
    report.status = payload.status
    report.updated_at = utcnow()
    db.add(ReportHistory(report_id=report.id, actor_id=user.id, old_status=old_status, new_status=payload.status, note=payload.note))
    db.commit()
    return load_report(db, report.id)


@router.post("/{report_id}/disposisi", response_model=ReportResponse)
def disposition_report(
    report_id: int,
    payload: DispositionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemda")),
):
    """Catat disposisi laporan untuk tindak lanjut unit/tujuan terkait."""
    report = load_report(db, report_id)
    if not is_report_in_admin_scope(report, user):
        raise HTTPException(status_code=403, detail="Laporan di luar wilayah tugas")

    note = f"Disposisi kepada {payload.tujuan.strip()}: {payload.catatan.strip()}"
    db.add(ReportHistory(
        report_id=report.id,
        actor_id=user.id,
        old_status=report.status,
        new_status=report.status,
        note=note,
    ))
    report.updated_at = utcnow()
    db.commit()
    return load_report(db, report.id)
