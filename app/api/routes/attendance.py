from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession, require_roles, school_id_for
from app.models.academics import Attendance, ClassSection
from app.models.core import User
from app.models.enums import AttendanceStatus, Role
from app.models.people import Staff, Student
from app.schemas.academics import AttendanceMark
from app.services.audit import audit

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.post("", status_code=201)
async def mark_attendance(payload: AttendanceMark, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF, Role.TEACHER))) -> dict:
    school_id = school_id_for(actor)
    if bool(payload.student_id) == bool(payload.staff_id):
        raise HTTPException(status_code=400, detail="Provide exactly one of student_id or staff_id")
    if payload.status not in {s.value for s in AttendanceStatus}:
        raise HTTPException(status_code=400, detail="Invalid attendance status")
    if payload.student_id:
        student = await db.scalar(select(Student).where(Student.id == payload.student_id, Student.school_id == school_id))
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        if payload.class_section_id:
            section = await db.scalar(select(ClassSection).where(ClassSection.id == payload.class_section_id, ClassSection.school_id == school_id))
            if not section:
                raise HTTPException(status_code=404, detail="Class section not found")
    if payload.staff_id:
        staff = await db.scalar(select(Staff).where(Staff.id == payload.staff_id, Staff.school_id == school_id))
        if not staff:
            raise HTTPException(status_code=404, detail="Staff member not found")
    record = Attendance(school_id=school_id, marked_by_user_id=actor.id, **payload.model_dump())
    db.add(record)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Attendance already marked for this person/date") from exc
    await audit(db, actor, "attendance.mark", "attendance", record.id, {"status": record.status})
    await db.commit()
    return {"id": record.id, **payload.model_dump(), "marked_by_user_id": actor.id}


@router.get("/sections/{section_id}")
async def section_attendance(section_id: int, attendance_date: str, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF, Role.TEACHER))) -> list[dict]:
    try:
        day = date.fromisoformat(attendance_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="attendance_date must be YYYY-MM-DD") from exc
    school_id = school_id_for(actor)
    rows = (await db.execute(select(Attendance, Student).join(Student, Student.id == Attendance.student_id).where(Attendance.school_id == school_id, Attendance.class_section_id == section_id, Attendance.attendance_date == day).order_by(Student.admission_no))).all()
    return [{"student_id": student.id, "admission_no": student.admission_no, "name": f"{student.first_name} {student.last_name}".strip(), "status": attendance.status, "notes": attendance.notes} for attendance, student in rows]
