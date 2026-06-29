from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal, TenantRow

ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login", auto_error=False)


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(tenant_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    return jwt.encode({"sub": tenant_id, "exp": expire}, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> str:
    """Return tenant_id or raise 401."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        tenant_id: str | None = payload.get("sub")
        if not tenant_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return tenant_id
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


# ── DB lookup ─────────────────────────────────────────────────────────────────

async def _get_tenant_by_id(tenant_id: str) -> TenantRow:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(TenantRow).where(TenantRow.tenant_id == tenant_id))
        tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant not found")
    return tenant


async def _get_tenant_by_api_key(api_key: str) -> TenantRow:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(TenantRow).where(TenantRow.api_key == api_key))
        tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return tenant


# ── FastAPI dependencies ──────────────────────────────────────────────────────

async def get_tenant_from_jwt(token: str = Depends(oauth2_scheme)) -> TenantRow:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    tenant_id = _decode_token(token)
    return await _get_tenant_by_id(tenant_id)


async def get_tenant_from_api_key(x_api_key: str = Header(...)) -> TenantRow:
    return await _get_tenant_by_api_key(x_api_key)


async def get_tenant(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    x_api_key: str | None = Header(default=None),
) -> TenantRow:
    """Tries JWT first, falls back to API key."""
    if token:
        tenant_id = _decode_token(token)
        tenant = await _get_tenant_by_id(tenant_id)
    elif x_api_key:
        tenant = await _get_tenant_by_api_key(x_api_key)
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    request.state.tenant_id = tenant.tenant_id
    return tenant


def require_admin(x_admin_key: str = Header(...)) -> None:
    if x_admin_key != settings.ADMIN_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key")
