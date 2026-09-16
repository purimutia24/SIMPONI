import base64
import hashlib
import hmac
import os
import time

TOKEN_TTL_SECONDS = 60 * 60 * 12


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"{base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_text, digest_text = stored_hash.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _secret() -> bytes:
    return os.getenv("SECRET_KEY", "dev-only-change-this-secret").encode()


def create_access_token(user_id: int) -> str:
    expires = int(time.time()) + TOKEN_TTL_SECONDS
    payload = f"{user_id}:{expires}"
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def get_user_id_from_token(token: str) -> int | None:
    try:
        user_text, expires_text, signature = token.split(":", 2)
        payload = f"{user_text}:{expires_text}"
        expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected) or int(expires_text) < int(time.time()):
            return None
        return int(user_text)
    except (ValueError, TypeError):
        return None
