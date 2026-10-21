import csv
import io
import json
from datetime import date, datetime, time
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models import AccessToken, Report, ReportHistory, User
from app.report_scope import DISTRICT_NAMES, scope_reports_to_user
from app.schemas import OfficerCreate, OfficerUpdate, ProvincialAdminCreate, StatisticUpdate, UserResponse
from app.security import hash_password

router = APIRouter(prefix="/admin", tags=["Administrasi"])
STATISTIC_FILE = Path(__file__).resolve().parents[1] / "data" / "pernikahan_dini.json"

NAMA_KABUPATEN = DISTRICT_NAMES

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _apply_date_filter(query, start_date: date | None, end_date: date | None):
    if start_date:
        query = query.where(Report.created_at >= datetime.combine(start_date, time.min))
    if end_date:
        query = query.where(Report.created_at <= datetime.combine(end_date, time.max))
    return query


def _scoped_query(user: User, kode_kabupaten: int | None = None):
    """Buat base query Report yang sudah disaring sesuai role."""
    query = scope_reports_to_user(select(Report), user)
    if user.role != "admin_pemda" and kode_kabupaten:
        query = query.where(Report.kode_kabupaten == kode_kabupaten)
    return query


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard(
    db: Session = Depends(get_db), 
    user: User = Depends(require_roles("admin_pemda", "admin_pemprov")),
):
    """Dashboard ringkasan: total laporan per status."""
    rows = db.scalars(_scoped_query(user)).all()
    statuses = ["Diajukan", "Diverifikasi", "Diproses", "Selesai", "Ditolak"]
    counts = {s: sum(r.status == s for r in rows) for s in statuses}
    return {
        "scope": user.kode_kabupaten if user.role == "admin_pemda" else "Jawa Barat",
        "nama_scope": NAMA_KABUPATEN.get(user.kode_kabupaten or 0, "Jawa Barat"),
        "total": len(rows),
        "by_status": counts,
        "queue": counts["Diajukan"] + counts["Diverifikasi"],
    }


@router.get("/dashboard/rapor-kabupaten")
def rapor_kabupaten(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemprov")),
):
    """
    Rapor Kerja Kabupaten — khusus Admin Pemprov.
    Menampilkan persentase penyelesaian per kabupaten,
    diurutkan dari yang paling lambat (% selesai terendah).
    """
    rows = db.scalars(select(Report)).all()

    # Agregasi per kabupaten
    by_kab: dict[int, dict] = {}
    for r in rows:
        k = r.kode_kabupaten
        if k not in by_kab:
            by_kab[k] = {"total": 0, "selesai": 0, "diproses": 0, "diajukan": 0, "ditolak": 0}
        by_kab[k]["total"] += 1
        status_lower = r.status.lower()
        if r.status == "Selesai":
            by_kab[k]["selesai"] += 1
        elif r.status == "Diproses":
            by_kab[k]["diproses"] += 1
        elif r.status == "Diajukan":
            by_kab[k]["diajukan"] += 1
        elif r.status == "Ditolak":
            by_kab[k]["ditolak"] += 1

    hasil = []
    for kode, stat in by_kab.items():
        total = stat["total"]
        persen_selesai = round((stat["selesai"] / total) * 100, 1) if total > 0 else 0
        persen_belum = round(100 - persen_selesai, 1)
        hasil.append({
            "kode_kabupaten": kode,
            "nama_kabupaten": NAMA_KABUPATEN.get(kode, f"Kode {kode}"),
            "total_laporan": total,
            "selesai": stat["selesai"],
            "diproses": stat["diproses"],
            "diajukan": stat["diajukan"],
            "ditolak": stat["ditolak"],
            "persen_selesai": persen_selesai,
            "persen_belum_selesai": persen_belum,
            "rapor": "merah" if persen_selesai < 40 else ("kuning" if persen_selesai < 70 else "hijau"),
        })

    # Urutkan: % selesai terendah (terburuk) di atas
    hasil.sort(key=lambda x: x["persen_selesai"])

    return {
        "total_kabupaten_aktif": len(hasil),
        "kabupaten_rapor_merah": sum(1 for h in hasil if h["rapor"] == "merah"),
        "kabupaten_volume_tertinggi": max(hasil, key=lambda x: x["total_laporan"])["nama_kabupaten"] if hasil else None,
        "kabupaten_terlambat": hasil[0]["nama_kabupaten"] if hasil else None,
        "data": hasil,
    }


# ─── Manajemen Petugas ────────────────────────────────────────────────────────

@router.post("/officers", response_model=UserResponse, status_code=201)
def create_officer(
    payload: OfficerCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemprov")),
):
    """Buat akun petugas Admin Pemda baru."""
    if db.scalar(select(User).where((User.nip == payload.nip) | (User.email == payload.email))):
        raise HTTPException(status_code=409, detail="NIP atau email sudah digunakan")
    officer = User(
        nip=payload.nip,
        email=payload.email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role="admin_pemda",
        kode_kabupaten=payload.kode_kabupaten,
        email_verified=True,
    )
    db.add(officer)
    db.commit()
    db.refresh(officer)
    return officer


@router.get("/officers", response_model=list[UserResponse])
def list_officers(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemprov")),
):
    """Daftar semua petugas Admin Pemda."""
    return db.scalars(select(User).where(User.role == "admin_pemda").order_by(User.full_name)).all()


@router.patch("/officers/{officer_id}", response_model=UserResponse)
def update_officer(
    officer_id: int,
    payload: OfficerUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemprov")),
):
    """Perbarui informasi akun petugas Admin Pemda."""
    officer = db.get(User, officer_id)
    if not officer or officer.role != "admin_pemda":
        raise HTTPException(status_code=404, detail="Petugas tidak ditemukan")

    values = payload.model_dump(exclude_unset=True)
    if payload.password is not None:
        values["password_hash"] = hash_password(values.pop("password"))
    else:
        values.pop("password", None)

    if not values:
        raise HTTPException(status_code=422, detail="Minimal satu data petugas harus diperbarui")

    if "nip" in values or "email" in values:
        duplicate = db.scalar(
            select(User).where(
                User.id != officer_id,
                (User.nip == values.get("nip", officer.nip))
                | (func.lower(User.email) == values.get("email", officer.email).lower()),
            )
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="NIP atau email sudah digunakan")

    for field, value in values.items():
        setattr(officer, field, value)
    db.commit()
    db.refresh(officer)
    return officer


@router.delete("/officers/{officer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_officer(
    officer_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemprov")),
):
    """Hapus akun petugas dan pertahankan riwayat aksi tanpa identitas akun."""
    officer = db.get(User, officer_id)
    if not officer or officer.role != "admin_pemda":
        raise HTTPException(status_code=404, detail="Petugas tidak ditemukan")

    db.execute(
        update(ReportHistory)
        .where(ReportHistory.actor_id == officer_id)
        .values(actor_id=None)
    )
    db.execute(delete(AccessToken).where(AccessToken.user_id == officer_id))
    db.delete(officer)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/provincial-admins", response_model=UserResponse, status_code=201)
def create_provincial_admin(
    payload: ProvincialAdminCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemprov")),
):
    """Buat akun Admin Pemprov lain; hanya dapat dilakukan Admin Pemprov."""
    if db.scalar(select(User).where((User.nip == payload.nip) | (User.email == payload.email))):
        raise HTTPException(status_code=409, detail="NIP atau email sudah digunakan")
    admin_user = User(
        nip=payload.nip,
        email=payload.email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role="admin_pemprov",
        kode_kabupaten=None,
        is_active=True,
        email_verified=True,
    )
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)
    return admin_user


@router.get("/provincial-admins", response_model=list[UserResponse])
def list_provincial_admins(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemprov")),
):
    """Daftar akun Admin Pemprov agar jumlah dan pemilik akun dapat dipantau."""
    return db.scalars(
        select(User).where(User.role == "admin_pemprov").order_by(User.full_name)
    ).all()


@router.patch("/officers/{officer_id}/active", response_model=UserResponse)
def set_officer_active(
    officer_id: int,
    active: bool = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemprov")),
):
    """Aktifkan atau nonaktifkan akun petugas Pemda."""
    officer = db.get(User, officer_id)
    if not officer or officer.role != "admin_pemda":
        raise HTTPException(status_code=404, detail="Petugas tidak ditemukan")
    officer.is_active = active
    db.commit()
    db.refresh(officer)
    return officer


# ─── Manajemen Statistik ──────────────────────────────────────────────────────

@router.post("/statistics", status_code=201)
def upsert_statistic(
    payload: StatisticUpdate,
    user: User = Depends(require_roles("admin_pemprov")),
):
    """Tambah atau perbarui data statistik pernikahan dini tahunan."""
    data = json.loads(STATISTIC_FILE.read_text(encoding="utf-8")) if STATISTIC_FILE.exists() else []
    item = payload.model_dump()
    item["id"] = max((row.get("id", 0) for row in data), default=0) + 1
    for index, row in enumerate(data):
        if (
            row.get("tahun") == payload.tahun
            and row.get("kode_kabupaten_kota") == payload.kode_kabupaten_kota
            and row.get("jenis_kelamin") == payload.jenis_kelamin
        ):
            item["id"] = row.get("id", item["id"])
            data[index] = item
            break
    else:
        data.append(item)
    STATISTIC_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "success", "data": item}


# ─── Ekspor ───────────────────────────────────────────────────────────────────

_EXPORT_HEADERS = [
    "ID Laporan", "Nama Pelapor", "NIK Pelapor", "Telepon", "Email Pelapor",
    "Domisili Pelapor", "Hubungan dengan Kasus", "Usia Calon Perempuan",
    "Usia Calon Laki-Laki", "Status Pendidikan", "Kabupaten Kejadian",
    "Kecamatan/Desa Kejadian", "Waktu Rencana Akad", "Faktor Pendorong",
    "Kronologi/Deskripsi", "Dokumen Pendukung", "Kode Kabupaten",
    "Status Penanganan", "Tanggal Masuk", "Terakhir Diperbarui",
]

def _report_to_row(report: Report, reporter: User) -> list:
    return [
        report.id,
        report.pelapor_nama,
        report.pelapor_nik,
        report.pelapor_telepon,
        report.pelapor_email,
        report.pelapor_domisili,
        report.hubungan_pelapor,
        report.usia_perempuan,
        report.usia_laki_laki,
        report.status_pendidikan,
        report.lokasi_kabupaten,
        report.lokasi_kecamatan_desa,
        report.waktu_rencana_akad,
        report.faktor_pendorong,
        report.description,
        report.dokumen_pendukung or "-",
        report.kode_kabupaten,
        report.status,
        report.created_at.strftime("%d/%m/%Y %H:%M"),
        report.updated_at.strftime("%d/%m/%Y %H:%M"),
    ]


@router.get("/export.csv")
def export_reports_csv(
    start_date: date | None = None,
    end_date: date | None = None,
    kode_kabupaten: int | None = Query(default=None, ge=3201, le=3279),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemda", "admin_pemprov")),
):
    """Ekspor rekap laporan ke format CSV."""
    query = select(Report, User).join(User, User.id == Report.reporter_id).order_by(Report.created_at)
    query = scope_reports_to_user(query, user)
    if user.role != "admin_pemda" and kode_kabupaten:
        query = query.where(Report.kode_kabupaten == kode_kabupaten)
    query = _apply_date_filter(query, start_date, end_date)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_EXPORT_HEADERS)
    for report, reporter in db.execute(query):
        writer.writerow(_report_to_row(report, reporter))
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=rekap-laporan.csv"},
    )


@router.get("/export.xlsx")
def export_reports_xlsx(
    start_date: date | None = None,
    end_date: date | None = None,
    kode_kabupaten: int | None = Query(default=None, ge=3201, le=3279),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin_pemda", "admin_pemprov")),
):
    """Ekspor rekap laporan ke format Excel (.xlsx) dengan styling."""
    query = select(Report, User).join(User, User.id == Report.reporter_id).order_by(Report.created_at)
    query = scope_reports_to_user(query, user)
    if user.role != "admin_pemda" and kode_kabupaten:
        query = query.where(Report.kode_kabupaten == kode_kabupaten)
    query = _apply_date_filter(query, start_date, end_date)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rekap Laporan"

    # Header styling
    header_fill = PatternFill(start_color="1F3864", end_color="1F3864", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.append(_EXPORT_HEADERS)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    ws.row_dimensions[1].height = 36

    # Data rows
    alt_fill = PatternFill(start_color="EEF2F7", end_color="EEF2F7", fill_type="solid")
    for idx, (report, reporter) in enumerate(db.execute(query), start=2):
        ws.append(_report_to_row(report, reporter))
        if idx % 2 == 0:
            for cell in ws[idx]:
                cell.fill = alt_fill
        # Status cell warna
        status_cell = ws.cell(row=idx, column=18)
        status_colors = {
            "Diajukan": "FFC107", "Diverifikasi": "17A2B8",
            "Diproses": "007BFF", "Selesai": "28A745", "Ditolak": "DC3545",
        }
        color = status_colors.get(report.status)
        if color:
            status_cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
            status_cell.font = Font(color="FFFFFF", bold=True)

    # Auto column width
    col_widths = [8, 22, 18, 16, 28, 22, 24, 12, 12, 22, 22, 28, 18, 30, 50, 30, 10, 14, 18, 18]
    for col_idx, width in enumerate(col_widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width

    # Freeze header row
    ws.freeze_panes = "A2"

    # Tambah sheet Ringkasan
    ws_sum = wb.create_sheet("Ringkasan")
    scope_name = NAMA_KABUPATEN.get(user.kode_kabupaten or 0, "Jawa Barat") if user.role == "admin_pemda" else "Jawa Barat"
    filter_info = f"{start_date or 'Awal'} s/d {end_date or 'Sekarang'}"
    ws_sum.append(["SIMPONI — Rekap Laporan Pernikahan Dini"])
    ws_sum.append([f"Wilayah: {scope_name}"])
    ws_sum.append([f"Periode: {filter_info}"])
    ws_sum.append([f"Diekspor pada: {datetime.now().strftime('%d/%m/%Y %H:%M')}"])
    ws_sum.append([])
    ws_sum.append(["Status", "Jumlah"])
    all_reports = db.scalars(
        _scoped_query(user, kode_kabupaten)
    ).all()
    statuses = ["Diajukan", "Diverifikasi", "Diproses", "Selesai", "Ditolak"]
    for s in statuses:
        ws_sum.append([s, sum(1 for r in all_reports if r.status == s)])
    ws_sum.append(["Total", len(all_reports)])
    ws_sum.column_dimensions["A"].width = 20
    ws_sum.column_dimensions["B"].width = 12

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=rekap-laporan.xlsx"},
    )
