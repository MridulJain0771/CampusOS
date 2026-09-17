from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update

from app.api.deps import DbSession, require_roles, school_id_for
from app.models.academics import Enrollment
from app.models.core import User
from app.models.enums import Role
from app.models.operations import LifecycleEvent
from app.models.people import IdentityCard, Staff, Student
from app.schemas.operations import LifecycleChange
from app.services.audit import audit

router = APIRouter(prefix="/lifecycle", tags=["student & staff lifecycle"])


async def _record_event(db: DbSession, actor: User, entity_type: str, entity_id: int, event_type: str, payload: LifecycleChange) -> LifecycleEvent:
    event = LifecycleEvent(
        school_id=school_id_for(actor),
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        effective_on=payload.effective_on,
        reason=payload.reason,
        notes=payload.notes,
        actor_user_id=actor.id,
    )
    db.add(event)
    await db.flush()
    await audit(db, actor, f"{entity_type}.{event_type}", entity_type, entity_id, {"reason": payload.reason, "effective_on": payload.effective_on.isoformat()})
    return event


def _event_dict(event: LifecycleEvent) -> dict:
    return {
        "id": event.id,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "event_type": event.event_type,
        "effective_on": event.effective_on,
        "reason": event.reason,
        "notes": event.notes,
        "actor_user_id": event.actor_user_id,
        "created_at": event.created_at,
    }


@router.post("/students/{student_id}/withdraw")
async def withdraw_student(student_id: int, payload: LifecycleChange, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF))) -> dict:
    school_id = school_id_for(actor)
    student = await db.scalar(select(Student).where(Student.id == student_id, Student.school_id == school_id))
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    if not student.is_active:
        raise HTTPException(status_code=409, detail="Student is already inactive")
    student.is_active = False
    await db.execute(update(Enrollment).where(Enrollment.school_id == school_id, Enrollment.student_id == student_id).values(is_active=False))
    await db.execute(update(IdentityCard).where(IdentityCard.school_id == school_id, IdentityCard.holder_type == "student", IdentityCard.holder_id == student_id).values(is_active=False))
    if student.user_id:
        await db.execute(update(User).where(User.id == student.user_id).values(is_active=False))
    event = await _record_event(db, actor, "student", student_id, "withdrawn", payload)
    await db.commit()
    return {"student_id": student_id, "status": "inactive", "event": _event_dict(event)}


@router.post("/students/{student_id}/readmit")
async def readmit_student(student_id: int, payload: LifecycleChange, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF))) -> dict:
    school_id = school_id_for(actor)
    student = await db.scalar(select(Student).where(Student.id == student_id, Student.school_id == school_id))
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    student.is_active = True
    if student.user_id:
        await db.execute(update(User).where(User.id == student.user_id).values(is_active=True))
    event = await _record_event(db, actor, "student", student_id, "readmitted", payload)
    await db.commit()
    return {"student_id": student_id, "status": "active", "event": _event_dict(event), "next_step": "Create/activate the academic-year class enrollment."}


@router.post("/staff/{staff_id}/terminate")
async def terminate_staff(staff_id: int, payload: LifecycleChange, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN))) -> dict:
    school_id = school_id_for(actor)
    staff = await db.scalar(select(Staff).where(Staff.id == staff_id, Staff.school_id == school_id))
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    if not staff.is_active:
        raise HTTPException(status_code=409, detail="Staff member is already inactive")
    staff.is_active = False
    await db.execute(update(IdentityCard).where(IdentityCard.school_id == school_id, IdentityCard.holder_type == "staff", IdentityCard.holder_id == staff_id).values(is_active=False))
    if staff.user_id:
        await db.execute(update(User).where(User.id == staff.user_id).values(is_active=False))
    event = await _record_event(db, actor, "staff", staff_id, "terminated", payload)
    await db.commit()
    return {"staff_id": staff_id, "status": "inactive", "is_teacher": staff.is_teacher, "event": _event_dict(event)}


@router.post("/staff/{staff_id}/rehire")
async def rehire_staff(staff_id: int, payload: LifecycleChange, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN))) -> dict:
    school_id = school_id_for(actor)
    staff = await db.scalar(select(Staff).where(Staff.id == staff_id, Staff.school_id == school_id))
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    staff.is_active = True
    if staff.user_id:
        await db.execute(update(User).where(User.id == staff.user_id).values(is_active=True))
    event = await _record_event(db, actor, "staff", staff_id, "rehired", payload)
    await db.commit()
    return {"staff_id": staff_id, "status": "active", "event": _event_dict(event)}


@router.get("/{entity_type}/{entity_id}/history")
async def lifecycle_history(entity_type: str, entity_id: int, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF, Role.TEACHER))) -> list[dict]:
    if entity_type not in {"student", "staff"}:
        raise HTTPException(status_code=400, detail="entity_type must be student or staff")
    rows = (await db.scalars(select(LifecycleEvent).where(LifecycleEvent.school_id == school_id_for(actor), LifecycleEvent.entity_type == entity_type, LifecycleEvent.entity_id == entity_id).order_by(LifecycleEvent.effective_on, LifecycleEvent.id))).all()
    return [_event_dict(row) for row in rows]
