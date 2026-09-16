from datetime import datetime, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import ForgotPasswordRequest, LoginRequest, RegisterRequest, ResetPasswordRequest, TokenResponse, UserResponse
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Autentikasi"])


def serialize_user(user: User) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post("/register", response_model=TokenResponse, status_code=201)
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
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id), user=serialize_user(user))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(or_(User.nik == payload.identity, User.email == payload.identity.lower())))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Identitas atau kata sandi salah")
    return TokenResponse(access_token=create_access_token(user.id), user=serialize_user(user))


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    response = {"status": "success", "message": "Jika email terdaftar, tautan pemulihan telah dikirim."}
    if user:
        user.reset_token = secrets.token_urlsafe(32)
        user.reset_expires_at = datetime.utcnow() + timedelta(minutes=30)
        db.commit()
        response["reset_token"] = user.reset_token
    return response


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.reset_token == payload.token))
    if not user or not user.reset_expires_at or user.reset_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Tautan pemulihan tidak valid atau sudah kedaluwarsa")
    user.password_hash = hash_password(payload.password)
    user.reset_token = None
    user.reset_expires_at = None
    db.commit()
    return {"status": "success", "message": "Kata sandi berhasil diperbarui"}


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return serialize_user(user)
