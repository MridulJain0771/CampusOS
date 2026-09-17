from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.core import User
from app.models.enums import Role


async def bootstrap_superadmin() -> None:
    if not settings.bootstrap_superadmin_email or not settings.bootstrap_superadmin_password:
        return
    async with SessionLocal() as db:
        existing = await db.scalar(select(User).where(User.email == settings.bootstrap_superadmin_email))
        if existing:
            return
        db.add(
            User(
                school_id=None,
                email=settings.bootstrap_superadmin_email,
                full_name="Platform Super Admin",
                password_hash=hash_password(settings.bootstrap_superadmin_password),
                role=Role.SUPER_ADMIN.value,
            )
        )
        await db.commit()
