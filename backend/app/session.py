import json
import uuid

import redis.asyncio as aioredis

from app.config import settings

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _key(tenant_id: str, session_id: str) -> str:
    return f"session:{tenant_id}:{session_id}"


async def get_history(tenant_id: str, session_id: str) -> list[dict]:
    raw = await get_redis().get(_key(tenant_id, session_id))
    return json.loads(raw) if raw else []


async def save_history(tenant_id: str, session_id: str, history: list[dict]) -> None:
    r = get_redis()
    key = _key(tenant_id, session_id)
    await r.set(key, json.dumps(history))
    await r.expire(key, settings.SESSION_TTL_SECONDS)


async def delete_session(tenant_id: str, session_id: str) -> None:
    await get_redis().delete(_key(tenant_id, session_id))


def new_session_id() -> str:
    return str(uuid.uuid4())
