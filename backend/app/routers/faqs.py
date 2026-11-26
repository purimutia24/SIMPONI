from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models import FAQ, FAQInitialization, User
from app.schemas import FAQCreate, FAQResponse, FAQUpdate

router = APIRouter(tags=["Pusat Bantuan"])

INITIAL_FAQS = [
    {
        "category": "Alur Pelaporan",
        "question": "Bagaimana cara mengirim laporan melalui SIMPONI?",
        "answer": "Masuk ke akun masyarakat, buka menu Pelaporan Kasus, lengkapi informasi yang diminta, lalu kirim laporan. Setelah berhasil, laporan dapat dipantau melalui menu Tracking Laporan.",
        "order_index": 1,
    },
    {
        "category": "Alur Pelaporan",
        "question": "Apakah saya perlu membuat akun untuk melapor?",
        "answer": "Ya. Fitur pelaporan dan tracking tersedia setelah Anda masuk sebagai pengguna masyarakat. Gunakan akun Anda agar perkembangan laporan dapat dilihat kembali.",
        "order_index": 2,
    },
    {
        "category": "Alur Pelaporan",
        "question": "Informasi apa yang perlu disiapkan sebelum membuat laporan?",
        "answer": "Siapkan informasi mengenai lokasi, waktu atau rencana kejadian, kondisi yang dilaporkan, serta dokumen pendukung bila tersedia. Isi keterangan dengan benar dan jelas agar laporan dapat ditindaklanjuti.",
        "order_index": 3,
    },
    {
        "category": "Privasi & Keamanan Data",
        "question": "Apakah identitas pelapor akan ditampilkan kepada publik?",
        "answer": "Tidak. Informasi pelapor bukan informasi publik dan digunakan untuk keperluan pengelolaan laporan sesuai pilihan kerahasiaan dan kebijakan layanan SIMPONI.",
        "order_index": 1,
    },
    {
        "category": "Privasi & Keamanan Data",
        "question": "Bagaimana menjaga keamanan akun SIMPONI?",
        "answer": "Gunakan kata sandi yang kuat, jangan membagikan kata sandi atau kode akses kepada orang lain, dan selalu keluar dari akun setelah menggunakan perangkat bersama.",
        "order_index": 2,
    },
    {
        "category": "Tindak Lanjut Kasus",
        "question": "Bagaimana cara mengetahui perkembangan laporan?",
        "answer": "Masuk menggunakan akun yang digunakan untuk melapor, lalu buka menu Tracking Laporan. Di sana Anda dapat melihat status dan riwayat perkembangan laporan.",
        "order_index": 1,
    },
    {
        "category": "Tindak Lanjut Kasus",
        "question": "Apa arti status laporan yang ditampilkan?",
        "answer": "Status menunjukkan tahapan penanganan laporan, seperti Diajukan, Diverifikasi, Diproses, Selesai, atau Ditolak. Catatan pada riwayat laporan dapat memberikan informasi tambahan dari petugas.",
        "order_index": 2,
    },
    {
        "category": "Kendala Akun",
        "question": "Apa yang harus dilakukan jika lupa kata sandi?",
        "answer": "Pada halaman masuk, pilih Lupa Kata Sandi dan ikuti instruksi pemulihan melalui email yang terdaftar.",
        "order_index": 1,
    },
    {
        "category": "Kendala Akun",
        "question": "Apa yang harus dilakukan jika tidak dapat masuk ke akun?",
        "answer": "Pastikan email atau identitas dan kata sandi sudah benar. Jika masih gagal, gunakan fitur pemulihan kata sandi atau hubungi layanan bantuan melalui informasi kontak di halaman ini.",
        "order_index": 2,
    },
]


def seed_initial_faqs(db: Session):
    initialization_key = "initial_faqs"
    if db.get(FAQInitialization, initialization_key) is not None:
        return

    if db.scalar(select(FAQ.id).limit(1)) is None:
        db.add_all(FAQ(**item, is_active=True) for item in INITIAL_FAQS)
    db.add(FAQInitialization(key=initialization_key))
    db.commit()


def _ordered_faqs():
    return select(FAQ).order_by(FAQ.order_index, FAQ.id)


@router.get("/faqs", response_model=list[FAQResponse])
def list_public_faqs(
    search: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
):
    query = _ordered_faqs().where(FAQ.is_active.is_(True))
    if category:
        query = query.where(FAQ.category == category)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            FAQ.question.ilike(term) | FAQ.answer.ilike(term) | FAQ.category.ilike(term)
        )
    return db.scalars(query).all()


@router.get("/admin/faqs", response_model=list[FAQResponse])
def list_admin_faqs(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("admin_pemprov")),
):
    return db.scalars(_ordered_faqs()).all()


@router.post(
    "/admin/faqs",
    response_model=FAQResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_faq(
    payload: FAQCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("admin_pemprov")),
):
    faq = FAQ(**payload.model_dump())
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq


@router.put("/admin/faqs/{faq_id}", response_model=FAQResponse)
def update_faq(
    faq_id: int,
    payload: FAQUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("admin_pemprov")),
):
    faq = db.get(FAQ, faq_id)
    if faq is None:
        raise HTTPException(status_code=404, detail="FAQ tidak ditemukan")

    for field, value in payload.model_dump().items():
        setattr(faq, field, value)
    db.commit()
    db.refresh(faq)
    return faq


@router.delete("/admin/faqs/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_faq(
    faq_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("admin_pemprov")),
):
    faq = db.get(FAQ, faq_id)
    if faq is None:
        raise HTTPException(status_code=404, detail="FAQ tidak ditemukan")
    db.delete(faq)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
