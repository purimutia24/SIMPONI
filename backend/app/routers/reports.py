import uuid
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models import Report, ReportHistory, User, utcnow
from app.report_scope import (
    DISTRICT_NAMES,
    district_code_from_name,
    is_report_in_admin_scope,
    scope_reports_to_user,
)
from app.schemas import DispositionCreate, ReportResponse, ReportUpdate

router = APIRouter(prefix="/reports", tags=["Laporan"])
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MINOR_AGE = 19
ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", *ALLOWED_PHOTO_EXTENSIONS}


def age_from_value(value: str) -> int | None:
    match = re.search(r"\d+", value.strip())
    return int(match.group()) if match else None


def load_report(db: Session, report_id: int) -> Report:
    report = db.scalar(
        select(Report).options(selectinload(Report.histories)).where(Report.id == report_id)
    )
    if not report:
        raise HTTPException(status_code=404, detail="Laporan tidak ditemukan")
    return report


def save_upload(upload: UploadFile | None, allowed_extensions: set[str]) -> str | None:
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
    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=415,
            detail=f"Jenis file tidak didukung. Gunakan: {', '.join(sorted(allowed_extensions))}",
        )
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
    kode_kabupaten: int = Form(...),
    lokasi_kecamatan_desa: str = Form(...),
    waktu_rencana_akad: str = Form(...),
    faktor_pendorong: str = Form(...),
    description: str = Form(..., min_length=100, max_length=10000),
    pernyataan_benar: bool = Form(...),
    setuju_pemrosesan: bool = Form(...),
    nama_perempuan: str = Form(""),
    nama_laki_laki: str = Form(""),
    foto_bukti_awal: UploadFile = File(None),
    foto_bukti: UploadFile = File(None),
    dokumen_pendukung_lain: UploadFile = File(None),
    dokumen_pendukung: UploadFile = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("public")),
    kerahasiaan: str = Form("rahasia"),
    pelapor_nama: str = Form(""),
):
    if not isinstance(kerahasiaan, str):
        kerahasiaan = "rahasia"
    if not isinstance(pelapor_nama, str):
        pelapor_nama = ""
    if not isinstance(nama_perempuan, str):
        nama_perempuan = ""
    if not isinstance(nama_laki_laki, str):
        nama_laki_laki = ""
    reporter_name = pelapor_nama.strip() or user.full_name.strip()
    if len(reporter_name) < 3 or not user.nik or not user.nik.isdigit() or len(user.nik) != 16:
        raise HTTPException(
            status_code=422,
            detail="Profil akun belum memiliki nama dan NIK yang valid",
        )
    if kerahasiaan not in {"anonim", "rahasia", "biasa"}:
        raise HTTPException(status_code=422, detail="Opsi kerahasiaan tidak valid")
    for field_name, value in (
        ("Nama perempuan", nama_perempuan),
        ("Nama laki-laki", nama_laki_laki),
    ):
        if value.strip() and len(value.strip()) < 3:
            raise HTTPException(status_code=422, detail=f"{field_name} minimal 3 karakter")
    if kode_kabupaten not in DISTRICT_NAMES:
        raise HTTPException(
            status_code=422,
            detail="Kabupaten/kota lokasi laporan tidak valid",
        )
    district_code = district_code_from_name(lokasi_kabupaten)
    if district_code is None and str(lokasi_kabupaten).strip() == str(kode_kabupaten):
        district_code = kode_kabupaten
    if district_code != kode_kabupaten:
        raise HTTPException(
            status_code=422,
            detail="Kode kabupaten/kota tidak sesuai dengan lokasi laporan",
        )
    female_age = age_from_value(usia_perempuan)
    male_age = age_from_value(usia_laki_laki)
    if female_age is None or male_age is None:
        raise HTTPException(
            status_code=422,
            detail="Usia kedua calon mempelai harus diisi dengan angka",
        )
    if female_age >= MINOR_AGE and male_age >= MINOR_AGE:
        raise HTTPException(
            status_code=422,
            detail="Laporan hanya dapat dibuat jika minimal salah satu calon mempelai berusia di bawah 19 tahun",
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
        if  upload and upload.filename:
            upload.file.seek(0, 2)
            size = upload.file.tell()
            upload.file.seek(0)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Ukuran setiap file maksimal 2 MB",
                )

    saved_paths: list[Path] = []
    try:
        if photo_upload and photo_upload.filename:
            foto_bukti_awal_path = save_upload(photo_upload, ALLOWED_PHOTO_EXTENSIONS)
            saved_paths.append(UPLOAD_DIR / Path(foto_bukti_awal_path).name)
        else:
            foto_bukti_awal_path = None
        if document_upload and document_upload.filename:
            dokumen_pendukung_path = save_upload(document_upload, ALLOWED_DOCUMENT_EXTENSIONS)
            saved_paths.append(UPLOAD_DIR / Path(dokumen_pendukung_path).name)
        else:
            dokumen_pendukung_path = None
    except OSError as error:
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="Bukti gagal disimpan di server") from error

    nama_perempuan_value = nama_perempuan.strip() if isinstance(nama_perempuan, str) else ""
    nama_laki_laki_value = nama_laki_laki.strip() if isinstance(nama_laki_laki, str) else ""
    report = Report(
        reporter_id=None if kerahasiaan == "anonim" else user.id,
        kode_kabupaten=kode_kabupaten,
        pelapor_nama="Anonim" if kerahasiaan == "anonim" else reporter_name,
        pelapor_nik="0000000000000000" if kerahasiaan == "anonim" else user.nik,
        pelapor_telepon="" if kerahasiaan == "anonim" else pelapor_telepon,
        pelapor_email="" if kerahasiaan == "anonim" else pelapor_email,
        pelapor_domisili="" if kerahasiaan == "anonim" else pelapor_domisili,
        hubungan_pelapor=hubungan_pelapor, nama_perempuan=nama_perempuan_value or None,
        nama_laki_laki=nama_laki_laki_value or None, usia_perempuan=usia_perempuan,
        usia_laki_laki=usia_laki_laki, status_pendidikan=status_pendidikan,
        lokasi_kabupaten=lokasi_kabupaten, lokasi_kecamatan_desa=lokasi_kecamatan_desa, waktu_rencana_akad=waktu_rencana_akad,
        faktor_pendorong=faktor_pendorong, description=description.strip(),
        foto_bukti_awal=foto_bukti_awal_path, dokumen_pendukung=dokumen_pendukung_path,
        pernyataan_benar=pernyataan_benar, setuju_pemrosesan=setuju_pemrosesan,
        kerahasiaan=kerahasiaan,
    )
    try:
        db.add(report)
        db.flush()
        db.add(ReportHistory(report_id=report.id, actor_id=user.id, new_status="Diajukan", note="Laporan dibuat oleh pelapor"))
        db.commit()
    except Exception:
        db.rollback()
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise
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
