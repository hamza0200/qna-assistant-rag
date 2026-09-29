"""Liveness/readiness endpoint used by Docker healthchecks and uptime monitors."""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Return app status and whether the database answers a trivial query.

    Responds 503 when the DB is down so load balancers stop routing to us.
    """
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:  # noqa: BLE001 - any DB failure means "not ready"
        logger.exception("health_db_check_failed")
        db_status = "unavailable"

    ok = db_status == "ok"
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "status": "ok" if ok else "degraded",
            "app": get_settings().app_name,
            "database": db_status,
        },
    )
