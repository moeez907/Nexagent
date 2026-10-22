"""Password and cookie-session helpers for application authentication."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AuthSessionModel, UserModel

SESSION_COOKIE = "awa_session"
SESSION_TTL_DAYS = 30


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 240_000)
        return hmac.compare_digest(expected.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(db: AsyncSession, user: UserModel) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthSessionModel(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=datetime.utcnow() + timedelta(days=SESSION_TTL_DAYS),
    ))
    await db.commit()
    return token


async def get_user_from_token(db: AsyncSession, token: str | None) -> UserModel | None:
    if not token:
        return None
    result = await db.execute(
        select(AuthSessionModel).where(
            AuthSessionModel.token_hash == hash_token(token),
            AuthSessionModel.revoked_at.is_(None),
            AuthSessionModel.expires_at > datetime.utcnow(),
        )
    )
    auth_session = result.scalar_one_or_none()
    if not auth_session:
        return None
    user_result = await db.execute(select(UserModel).where(UserModel.id == auth_session.user_id))
    return user_result.scalar_one_or_none()


async def get_optional_user(db: AsyncSession, token: str | None) -> UserModel | None:
    return await get_user_from_token(db, token)
