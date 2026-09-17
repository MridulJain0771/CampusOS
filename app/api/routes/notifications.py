from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, school_id_for
from app.models.core import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(db: DbSession, actor: CurrentUser) -> list[dict]:
    rows = (await db.scalars(select(Notification).where(Notification.school_id == school_id_for(actor), Notification.user_id == actor.id).order_by(Notification.created_at.desc()).limit(100))).all()
    return [{"id": n.id, "kind": n.kind, "title": n.title, "message": n.message, "read_at": n.read_at, "created_at": n.created_at} for n in rows]


@router.post("/{notification_id}/read")
async def mark_read(notification_id: int, db: DbSession, actor: CurrentUser) -> dict:
    notification = await db.scalar(select(Notification).where(Notification.id == notification_id, Notification.school_id == school_id_for(actor), Notification.user_id == actor.id))
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.read_at = datetime.now(UTC)
    await db.commit()
    return {"id": notification.id, "read_at": notification.read_at}
