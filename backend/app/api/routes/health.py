import logging

import psycopg
from fastapi import APIRouter, HTTPException
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.db.mongo import get_mongo_client
from app.db.redis_store import get_redis_client

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
def health_check() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@router.get("/ready", include_in_schema=False)
def readiness_check() -> dict[str, str]:
    """Private container readiness check for all durable/runtime dependencies."""
    settings = get_settings()
    try:
        with psycopg.connect(settings.postgres_dsn, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
        get_mongo_client().admin.command("ping")
        get_redis_client().ping()
    except (psycopg.Error, PyMongoError, RedisError, OSError) as exc:
        logger.warning("Readiness dependency unavailable: %s", type(exc).__name__)
        raise HTTPException(503, detail="Dependency unavailable") from None
    return {"status": "ready"}
