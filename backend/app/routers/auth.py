from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr
import json
import logging
import os
import secrets
import smtplib
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import bearer_scheme, get_current_user
from app.models import AccessToken, User, utcnow
from app.schemas import ForgotPasswordRequest, LoginRequest, RegisterRequest, ResetPasswordRequest, TokenResponse, UserResponse, VerificationResponse
from app.security import create_access_token, get_access_token_expiry, hash_password, hash_token, verify_password

load_dotenv()
router = APIRouter(prefix="/auth", tags=["Autentikasi"])
logger = logging.getLogger(__name__)


def send_email(recipient: str, subject: str, body: str) -> None:
    default_provider = "resend" if os.getenv("RESEND_API_KEY") else "smtp"
    provider = os.getenv("EMAIL_PROVIDER", default_provider).strip().lower()
    if provider == "apps_script":
        relay_url = os.getenv("EMAIL_WEBHOOK_URL")
        relay_secret = os.getenv("EMAIL_WEBHOOK_SECRET")
        if not relay_url or not relay_secret:
            raise RuntimeError("EMAIL_WEBHOOK_URL dan EMAIL_WEBHOOK_SECRET harus dikonfigurasi")
        request = Request(
            relay_url,
            data=json.dumps({
                "secret": relay_secret,
                "to": recipient,
                "subject": subject,
                "text": body,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError("Google Apps Script menolak pengiriman email")
        return

    if provider == "resend":
        api_key = os.getenv("RESEND_API_KEY")
        sender = os.getenv("EMAIL_FROM", "")
        if not api_key or not sender:
            raise RuntimeError("RESEND_API_KEY dan EMAIL_FROM harus dikonfigurasi")
        request = Request(
            "https://api.resend.com/emails",
            data=json.dumps({
                "from": sender,
                "to": [recipient],
                "subject": subject,
                "text": body,
            }).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            response.read()
        return
    if provider != "smtp":
        raise RuntimeError("EMAIL_PROVIDER harus bernilai 'smtp' atau 'resend'")

    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not smtp_host or not smtp_user or not smtp_password or not smtp_from:
        raise RuntimeError("Konfigurasi SMTP belum lengkap")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(("SIMPONI", smtp_from))
    message["To"] = recipient
    message.set_content(body)

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(message)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(message)


def send_reset_email(recipient: str, reset_token: str) -> None:
    frontend_reset_url = os.getenv(
        "FRONTEND_RESET_URL",
        "http://localhost:5173/reset-password",
    )
    reset_url = f"{frontend_reset_url}?token={quote(reset_token)}"
    send_email(
        recipient,
        "Pemulihan kata sandi SIMPONI",
        "Kami menerima permintaan pemulihan kata sandi akun SIMPONI.\n\n"
        f"Buka tautan berikut untuk membuat kata sandi baru:\n{reset_url}\n\n"
        "Tautan ini berlaku selama 30 menit. Jika kamu tidak meminta pemulihan, "
        "abaikan email ini.",
    )


def send_verification_email(recipient: str, verification_token: str) -> None:
    frontend_verify_url = os.getenv(
        "FRONTEND_VERIFY_URL",
        "http://localhost:5173/verify-email",
    )
    verify_url = f"{frontend_verify_url}?token={quote(verification_token)}"
    send_email(
        recipient,
        "Verifikasi email akun SIMPONI",
        "Terima kasih telah mendaftar di SIMPONI.\n\n"
        f"Klik tautan berikut untuk memverifikasi email dan mengaktifkan akun:\n{verify_url}\n\n"
        "Tautan ini berlaku selama 30 menit. Jika kamu tidak membuat akun ini, abaikan email ini."
    )


def serialize_user(user: User) -> UserResponse:
    return UserResponse.model_validate(user)


def store_access_token(db: Session, user: User) -> str:
    token = create_access_token(user.id)
    db.add(AccessToken(
        token_hash=hash_token(token),
        user_id=user.id,
        expires_at=get_access_token_expiry(token),
    ))
    return token


@router.post("/register", response_model=VerificationResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    kode_kabupaten = int(payload.nik[:4])
    if not 3201 <= kode_kabupaten <= 3279:
        raise HTTPException(status_code=422, detail="NIK bukan wilayah Jawa Barat yang didukung")
    existing = db.scalar(select(User).where(or_(User.nik == payload.nik, User.email == payload.email)))
    if existing:
        raise HTTPException(status_code=409, detail="NIK atau email sudah terdaftar")
    user = User(
        nik=payload.nik,
        email=payload.email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        kode_kabupaten=kode_kabupaten,
        is_active=False,
        email_verified=False,
        verification_token=secrets.token_urlsafe(32),
        verification_expires_at=utcnow() + timedelta(minutes=30),
    )
    db.add(user)
    verification_token = user.verification_token
    user.verification_token = hash_token(verification_token)
    try:
        send_verification_email(user.email, verification_token)
    except (OSError, smtplib.SMTPException, ValueError, RuntimeError) as error:
        db.rollback()
        logger.exception("Gagal mengirim email verifikasi")
        raise HTTPException(status_code=503, detail="Email verifikasi gagal dikirim") from error
    db.commit()
    return VerificationResponse(
        status="pending",
        message="Registrasi berhasil. Periksa email untuk memverifikasi akun sebelum login.",
    )


def authenticate(payload: LoginRequest, db: Session, required_role: str) -> TokenResponse:
    identifier_column = User.nip if required_role in {"admin_pemda", "admin_pemprov"} else User.nik
    user = db.scalar(select(User).where(or_(identifier_column == payload.identity, User.email == payload.identity.lower())))
    if (
        not user
        or user.role != required_role
        or not user.is_active
        or (required_role == "public" and not user.email_verified)
        or not verify_password(payload.password, user.password_hash)
    ):
        if required_role == "admin_pemda":
            detail = (
                "NIP/email atau kata sandi salah, atau akun Admin Pemda tidak aktif. "
                "Periksa identitas dan minta Admin Pemprov memastikan akun aktif."
            )
        elif required_role == "admin_pemprov":
            detail = "NIP/email atau kata sandi Admin Pemprov salah."
        else:
            detail = "Identitas atau kata sandi salah"
        raise HTTPException(status_code=401, detail=detail)
    access_token = store_access_token(db, user)
    db.commit()
    return TokenResponse(access_token=access_token, user=serialize_user(user))


@router.post("/verify-email", response_model=VerificationResponse)
def verify_email(token: str, db: Session = Depends(get_db)):
    token_hash = hash_token(token.strip().strip('"'))
    user = db.scalar(select(User).where(User.verification_token == token_hash))
    if not user or not user.verification_expires_at or user.verification_expires_at < utcnow():
        raise HTTPException(status_code=400, detail="Token verifikasi tidak valid atau sudah kedaluwarsa")
    user.email_verified = True
    user.is_active = True
    user.verification_token = None
    user.verification_expires_at = None
    db.commit()
    return VerificationResponse(status="success", message="Email berhasil diverifikasi. Silakan login.")


@router.post("/resend-verification", response_model=VerificationResponse)
def resend_verification(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    response = VerificationResponse(
        status="success",
        message="Jika akun membutuhkan verifikasi, email verifikasi telah dikirim ulang.",
    )
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or user.role != "public" or user.email_verified:
        return response

    verification_token = secrets.token_urlsafe(32)
    user.verification_token = hash_token(verification_token)
    user.verification_expires_at = utcnow() + timedelta(minutes=30)
    try:
        send_verification_email(user.email, verification_token)
    except (OSError, smtplib.SMTPException, ValueError, RuntimeError):
        db.rollback()
        logger.exception("Gagal mengirim ulang email verifikasi")
        return response
    db.commit()
    return response


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    return authenticate(payload, db, "public")


@router.post("/login/admin-pemda", response_model=TokenResponse)
def login_admin_pemda(payload: LoginRequest, db: Session = Depends(get_db)):
    return authenticate(payload, db, "admin_pemda")


@router.post("/login/admin-pemprov", response_model=TokenResponse)
def login_admin_pemprov(payload: LoginRequest, db: Session = Depends(get_db)):
    return authenticate(payload, db, "admin_pemprov")


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    response = {"status": "success", "message": "Jika email terdaftar, tautan pemulihan telah dikirim."}
    if user:
        reset_token = secrets.token_urlsafe(32)
        user.reset_token = hash_token(reset_token)
        user.reset_expires_at = utcnow() + timedelta(minutes=30)
        try:
            send_reset_email(user.email, reset_token)
        except (OSError, smtplib.SMTPException, ValueError, RuntimeError) as error:
            db.rollback()
            logger.exception("Gagal mengirim email pemulihan")
            return response
        db.commit()
    return response


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    reset_token_hash = hash_token(payload.token)
    user = db.scalar(select(User).where(or_(User.reset_token == reset_token_hash, User.reset_token == payload.token)))
    if not user or not user.reset_expires_at or user.reset_expires_at < utcnow():
        raise HTTPException(status_code=400, detail="Tautan pemulihan tidak valid atau sudah kedaluwarsa")
    user.password_hash = hash_password(payload.password)
    user.reset_token = None
    user.reset_expires_at = None
    now = utcnow()
    db.query(AccessToken).filter(
        AccessToken.user_id == user.id,
        AccessToken.revoked_at.is_(None),
    ).update({AccessToken.revoked_at: now}, synchronize_session=False)
    db.commit()
    return {"status": "success", "message": "Kata sandi berhasil diperbarui"}


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    access_token = db.get(AccessToken, hash_token(credentials.credentials.strip()))
    access_token.revoked_at = utcnow()
    db.commit()
    return {"status": "success", "message": "Logout berhasil"}


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return serialize_user(user)
