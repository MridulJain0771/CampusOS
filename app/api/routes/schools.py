from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import DbSession, require_roles, school_id_for
from app.core.security import hash_password
from app.models.academics import AcademicYear
from app.models.core import AuditLog, School, User
from app.models.enums import Role
from app.schemas.auth import UserCreate, UserResponse
from app.schemas.school import AcademicYearCreate, SchoolCreate, SchoolResponse
from app.services.audit import audit

router = APIRouter(tags=["schools & admin"])


@router.post("/schools", response_model=SchoolResponse, status_code=201)
async def create_school(
    payload: SchoolCreate,
    db: DbSession,
    actor: User = Depends(require_roles(Role.SUPER_ADMIN)),
) -> SchoolResponse:
    if await db.scalar(select(School).where(School.code == payload.code)):
        raise HTTPException(status_code=409, detail="School code already exists")
    if await db.scalar(select(User).where(User.email == payload.admin_email)):
        raise HTTPException(status_code=409, detail="Admin email already exists")

    school = School(name=payload.name, code=payload.code, timezone=payload.timezone, currency=payload.currency)
    db.add(school)
    await db.flush()
    db.add(
        User(
            school_id=school.id,
            email=payload.admin_email,
            full_name=payload.admin_name,
            password_hash=hash_password(payload.admin_password),
            role=Role.SCHOOL_ADMIN.value,
        )
    )
    await audit(db, actor, "school.create", "school", school.id, {"code": school.code})
    await db.commit()
    await db.refresh(school)
    return SchoolResponse.model_validate(school)


@router.get("/schools")
async def list_schools(
    db: DbSession,
    _: User = Depends(require_roles(Role.SUPER_ADMIN)),
) -> list[SchoolResponse]:
    rows = (await db.scalars(select(School).order_by(School.name))).all()
    return [SchoolResponse.model_validate(row) for row in rows]


@router.post("/admin/users", response_model=UserResponse, status_code=201)
async def create_school_user(
    payload: UserCreate,
    db: DbSession,
    actor: User = Depends(require_roles(Role.SCHOOL_ADMIN)),
) -> UserResponse:
    if payload.role == Role.SUPER_ADMIN:
        raise HTTPException(status_code=400, detail="School admin cannot create super admins")
    if await db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email already exists")
    user = User(
        school_id=school_id_for(actor),
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role.value,
    )
    db.add(user)
    await db.flush()
    await audit(db, actor, "user.create", "user", user.id, {"role": user.role})
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/academic-years", status_code=201)
async def create_academic_year(
    payload: AcademicYearCreate,
    db: DbSession,
    actor: User = Depends(require_roles(Role.SCHOOL_ADMIN)),
) -> dict:
    school_id = school_id_for(actor)
    if payload.starts_on >= payload.ends_on:
        raise HTTPException(status_code=400, detail="Academic year dates are invalid")
    if payload.is_current:
        existing = (await db.scalars(select(AcademicYear).where(AcademicYear.school_id == school_id))).all()
        for year in existing:
            year.is_current = False
    year = AcademicYear(school_id=school_id, **payload.model_dump())
    db.add(year)
    await db.flush()
    await audit(db, actor, "academic_year.create", "academic_year", year.id)
    await db.commit()
    return {"id": year.id, **payload.model_dump()}


@router.get("/audit-logs")
async def audit_logs(
    db: DbSession,
    actor: User = Depends(require_roles(Role.SCHOOL_ADMIN)),
    limit: int = 100,
) -> list[dict]:
    school_id = school_id_for(actor)
    rows = (
        await db.scalars(
            select(AuditLog)
            .where(AuditLog.school_id == school_id)
            .order_by(AuditLog.created_at.desc())
            .limit(min(limit, 200))
        )
    ).all()
    return [
        {
            "id": r.id,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "details": r.details,
            "actor_user_id": r.actor_user_id,
            "created_at": r.created_at,
        }
        for r in rows
    ]
