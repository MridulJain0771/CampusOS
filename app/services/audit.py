from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import AuditLog, User


async def audit(
    db: AsyncSession,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: int | str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            school_id=actor.school_id,
            actor_user_id=actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details,
        )
    )
