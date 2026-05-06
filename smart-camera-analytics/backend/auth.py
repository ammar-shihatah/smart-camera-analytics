"""
Authentication & Authorization
JWT tokens, password hashing, RBAC permission checks.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production-xyz987")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", "8"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

# Role → allowed permissions. "*" means all.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "super_admin": ["*"],
    "admin": [
        "users.view", "users.create", "users.update", "users.delete",
        "branches.view", "branches.create", "branches.update", "branches.delete",
        "cameras.view", "cameras.manage",
        "zones.view", "zones.manage",
        "analytics.view", "reports.export",
        "alerts.view", "alerts.resolve",
        "employees.view", "employees.manage",
        "audit.view",
    ],
    "branch_manager": [
        "branches.view",
        "cameras.view", "cameras.manage",
        "zones.view", "zones.manage",
        "analytics.view", "reports.export",
        "alerts.view", "alerts.resolve",
        "employees.view",
    ],
    "operations_manager": [
        "branches.view",
        "cameras.view",
        "zones.view",
        "analytics.view", "reports.export",
        "alerts.view", "alerts.resolve",
    ],
    "receptionist": [
        "branches.view",
        "analytics.view",
        "alerts.view",
    ],
    "viewer": [
        "branches.view", "cameras.view", "zones.view",
        "analytics.view", "alerts.view",
    ],
}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def has_permission(role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, [])
    return "*" in perms or permission in perms


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    from models import User

    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise exc
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise exc
    return user


def require_permission(permission: str):
    """Dependency factory — use as Depends(require_permission('cameras.manage'))."""
    async def _check(current_user=Depends(get_current_user)):
        if not has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: requires '{permission}'",
            )
        return current_user
    return _check
