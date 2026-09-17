from datetime import date
from io import BytesIO
from uuid import uuid4

import qrcode
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DbSession, require_roles, school_id_for
from app.models.core import User
from app.models.enums import Role
from app.models.operations import LifecycleEvent
from app.models.people import IdentityCard, Parent, Staff, Student, StudentParent
from app.schemas.people import IdCardCreate, LinkParentRequest, ParentCreate, StaffCreate, StudentCreate
from app.services.audit import audit

router = APIRouter(prefix="/people", tags=["students, parents & staff"])
manager_roles = (Role.SCHOOL_ADMIN, Role.STAFF)


def student_dict(student: Student) -> dict:
    return {
        "id": student.id,
        "admission_no": student.admission_no,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "date_of_birth": student.date_of_birth,
        "gender": student.gender,
        "joined_on": student.joined_on,
        "is_active": student.is_active,
        "user_id": student.user_id,
    }


@router.post("/students", status_code=201)
async def create_student(
    payload: StudentCreate,
    db: DbSession,
    actor: User = Depends(require_roles(*manager_roles)),
) -> dict:
    school_id = school_id_for(actor)
    if await db.scalar(select(Student).where(Student.school_id == school_id, Student.admission_no == payload.admission_no)):
        raise HTTPException(status_code=409, detail="Admission number already exists")
    student = Student(school_id=school_id, **payload.model_dump())
    db.add(student)
    await db.flush()
    db.add(
        LifecycleEvent(
            school_id=school_id,
            entity_type="student",
            entity_id=student.id,
            event_type="admitted",
            effective_on=student.joined_on or date.today(),
            actor_user_id=actor.id,
        )
    )
    await audit(db, actor, "student.create", "student", student.id, {"admission_no": student.admission_no})
    await db.commit()
    return student_dict(student)


@router.get("/students")
async def list_students(
    db: DbSession,
    actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF, Role.TEACHER, Role.ACCOUNTANT)),
) -> list[dict]:
    rows = (await db.scalars(select(Student).where(Student.school_id == school_id_for(actor)).order_by(Student.admission_no))).all()
    return [student_dict(s) for s in rows]


@router.post("/staff", status_code=201)
async def create_staff(
    payload: StaffCreate,
    db: DbSession,
    actor: User = Depends(require_roles(Role.SCHOOL_ADMIN)),
) -> dict:
    school_id = school_id_for(actor)
    if await db.scalar(select(Staff).where(Staff.school_id == school_id, Staff.employee_no == payload.employee_no)):
        raise HTTPException(status_code=409, detail="Employee number already exists")
    staff = Staff(school_id=school_id, **payload.model_dump())
    db.add(staff)
    await db.flush()
    db.add(
        LifecycleEvent(
            school_id=school_id,
            entity_type="staff",
            entity_id=staff.id,
            event_type="joined",
            effective_on=staff.joined_on or date.today(),
            actor_user_id=actor.id,
        )
    )
    await audit(db, actor, "staff.create", "staff", staff.id, {"employee_no": staff.employee_no})
    await db.commit()
    return {
        "id": staff.id,
        "employee_no": staff.employee_no,
        "full_name": staff.full_name,
        "department": staff.department,
        "designation": staff.designation,
        "is_teacher": staff.is_teacher,
        "user_id": staff.user_id,
    }


@router.get("/staff")
async def list_staff(
    db: DbSession,
    actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF, Role.TEACHER)),
) -> list[dict]:
    rows = (await db.scalars(select(Staff).where(Staff.school_id == school_id_for(actor)).order_by(Staff.employee_no))).all()
    return [
        {
            "id": s.id,
            "employee_no": s.employee_no,
            "full_name": s.full_name,
            "department": s.department,
            "designation": s.designation,
            "is_teacher": s.is_teacher,
            "user_id": s.user_id,
        }
        for s in rows
    ]


@router.post("/parents", status_code=201)
async def create_parent(
    payload: ParentCreate,
    db: DbSession,
    actor: User = Depends(require_roles(*manager_roles)),
) -> dict:
    parent = Parent(school_id=school_id_for(actor), **payload.model_dump())
    db.add(parent)
    await db.flush()
    await audit(db, actor, "parent.create", "parent", parent.id)
    await db.commit()
    return {"id": parent.id, "full_name": parent.full_name, "phone": parent.phone, "email": parent.email}


@router.post("/students/{student_id}/parents/{parent_id}", status_code=201)
async def link_parent(
    student_id: int,
    parent_id: int,
    payload: LinkParentRequest,
    db: DbSession,
    actor: User = Depends(require_roles(*manager_roles)),
) -> dict:
    school_id = school_id_for(actor)
    student = await db.scalar(select(Student).where(Student.id == student_id, Student.school_id == school_id))
    parent = await db.scalar(select(Parent).where(Parent.id == parent_id, Parent.school_id == school_id))
    if not student or not parent:
        raise HTTPException(status_code=404, detail="Student or parent not found")
    link = StudentParent(school_id=school_id, student_id=student_id, parent_id=parent_id, **payload.model_dump())
    db.add(link)
    await db.flush()
    await audit(db, actor, "student.parent.link", "student", student_id, {"parent_id": parent_id})
    await db.commit()
    return {"id": link.id, "student_id": student_id, "parent_id": parent_id, **payload.model_dump()}


async def _create_id_card(db: DbSession, actor: User, holder_type: str, holder_id: int, expires_on) -> IdentityCard:
    school_id = school_id_for(actor)
    model = Student if holder_type == "student" else Staff
    holder = await db.scalar(select(model).where(model.id == holder_id, model.school_id == school_id))
    if not holder:
        raise HTTPException(status_code=404, detail=f"{holder_type.title()} not found")
    existing = await db.scalar(
        select(IdentityCard).where(
            IdentityCard.school_id == school_id,
            IdentityCard.holder_type == holder_type,
            IdentityCard.holder_id == holder_id,
        )
    )
    if existing:
        return existing
    card_number = f"{holder_type[:1].upper()}-{school_id}-{uuid4().hex[:10].upper()}"
    card = IdentityCard(
        school_id=school_id,
        holder_type=holder_type,
        holder_id=holder_id,
        card_number=card_number,
        qr_payload=f"campusos://school/{school_id}/{holder_type}/{holder_id}/card/{card_number}",
        expires_on=expires_on,
    )
    db.add(card)
    await db.flush()
    await audit(db, actor, "id_card.issue", "identity_card", card.id, {"holder_type": holder_type, "holder_id": holder_id})
    await db.commit()
    return card


@router.post("/students/{student_id}/id-card", status_code=201)
async def issue_student_card(
    student_id: int,
    payload: IdCardCreate,
    db: DbSession,
    actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF)),
) -> dict:
    card = await _create_id_card(db, actor, "student", student_id, payload.expires_on)
    return {"id": card.id, "card_number": card.card_number, "qr_payload": card.qr_payload, "expires_on": card.expires_on}


@router.post("/staff/{staff_id}/id-card", status_code=201)
async def issue_staff_card(
    staff_id: int,
    payload: IdCardCreate,
    db: DbSession,
    actor: User = Depends(require_roles(Role.SCHOOL_ADMIN)),
) -> dict:
    card = await _create_id_card(db, actor, "staff", staff_id, payload.expires_on)
    return {"id": card.id, "card_number": card.card_number, "qr_payload": card.qr_payload, "expires_on": card.expires_on}


@router.get("/id-cards/{card_id}/qr")
async def id_card_qr(
    card_id: int,
    db: DbSession,
    actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF, Role.TEACHER)),
) -> StreamingResponse:
    card = await db.scalar(select(IdentityCard).where(IdentityCard.id == card_id, IdentityCard.school_id == school_id_for(actor)))
    if not card:
        raise HTTPException(status_code=404, detail="ID card not found")
    image = qrcode.make(card.qr_payload)
    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return StreamingResponse(output, media_type="image/png")
