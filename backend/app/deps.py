from datetime import datetime

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AccessToken, User, utcnow
from app.security import get_user_id_from_token, hash_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Kirim header Authorization dengan format: Bearer <access_token> dari response login/register",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = get_user_id_from_token(credentials.credentials.strip())
    user = db.get(User, user_id) if user_id else None
    active_session = db.get(AccessToken, hash_token(credentials.credentials.strip()))
    if not user or not user.is_active or not active_session or active_session.revoked_at or active_session.expires_at <= utcnow():
        raise HTTPException(
            status_code=401,
            detail="Access token tidak valid atau akun tidak aktif. Login ulang dan gunakan token terbaru.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Anda tidak memiliki akses ke fitur ini")
        return user

    return dependency
