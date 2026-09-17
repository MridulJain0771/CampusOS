from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from app.db.session import SessionLocal

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request, response: Response) -> dict:
    checks = {"postgres": False, "redis": False}
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:
        pass
    try:
        checks["redis"] = bool(await request.app.state.redis.ping())
    except Exception:
        pass
    if not all(checks.values()):
        response.status_code = 503
        return {"status": "not_ready", "checks": checks}
    return {"status": "ready", "checks": checks}
