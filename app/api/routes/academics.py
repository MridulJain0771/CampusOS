from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import DbSession, require_roles, school_id_for
from app.models.academics import AcademicYear, Classroom, ClassSection, ClassSubjectTeacher, Enrollment, Subject, TimetableEntry
from app.models.core import User
from app.models.enums import Role
from app.models.people import Staff, Student
from app.schemas.academics import ClassroomCreate, EnrollmentCreate, SectionCreate, SubjectCreate, SubjectTeacherAssign, TimetableCreate
from app.services.audit import audit

router = APIRouter(prefix="/academics", tags=["classes & academics"])
admin_roles = (Role.SCHOOL_ADMIN, Role.STAFF)


@router.post("/classrooms", status_code=201)
async def create_classroom(payload: ClassroomCreate, db: DbSession, actor: User = Depends(require_roles(*admin_roles))) -> dict:
    room = Classroom(school_id=school_id_for(actor), **payload.model_dump())
    db.add(room)
    await db.flush()
    await audit(db, actor, "classroom.create", "classroom", room.id)
    await db.commit()
    return {"id": room.id, **payload.model_dump()}


@router.get("/classrooms")
async def list_classrooms(db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF, Role.TEACHER))) -> list[dict]:
    rows = (await db.scalars(select(Classroom).where(Classroom.school_id == school_id_for(actor)).order_by(Classroom.name))).all()
    return [{"id": r.id, "name": r.name, "building": r.building, "floor": r.floor, "capacity": r.capacity} for r in rows]


@router.post("/sections", status_code=201)
async def create_section(payload: SectionCreate, db: DbSession, actor: User = Depends(require_roles(*admin_roles))) -> dict:
    school_id = school_id_for(actor)
    year = await db.scalar(select(AcademicYear).where(AcademicYear.id == payload.academic_year_id, AcademicYear.school_id == school_id))
    if not year:
        raise HTTPException(status_code=404, detail="Academic year not found")
    if payload.classroom_id:
        room = await db.scalar(select(Classroom).where(Classroom.id == payload.classroom_id, Classroom.school_id == school_id))
        if not room:
            raise HTTPException(status_code=404, detail="Classroom not found")
    if payload.class_teacher_staff_id:
        teacher = await db.scalar(select(Staff).where(Staff.id == payload.class_teacher_staff_id, Staff.school_id == school_id, Staff.is_teacher.is_(True)))
        if not teacher:
            raise HTTPException(status_code=404, detail="Class teacher not found")
    section = ClassSection(school_id=school_id, **payload.model_dump())
    db.add(section)
    await db.flush()
    await audit(db, actor, "class_section.create", "class_section", section.id)
    await db.commit()
    return {"id": section.id, **payload.model_dump()}


@router.get("/sections")
async def list_sections(db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF, Role.TEACHER, Role.ACCOUNTANT))) -> list[dict]:
    rows = (await db.scalars(select(ClassSection).where(ClassSection.school_id == school_id_for(actor)).order_by(ClassSection.grade_name, ClassSection.section_name))).all()
    return [{"id": s.id, "academic_year_id": s.academic_year_id, "grade_name": s.grade_name, "section_name": s.section_name, "classroom_id": s.classroom_id, "class_teacher_staff_id": s.class_teacher_staff_id} for s in rows]


@router.post("/subjects", status_code=201)
async def create_subject(payload: SubjectCreate, db: DbSession, actor: User = Depends(require_roles(*admin_roles))) -> dict:
    subject = Subject(school_id=school_id_for(actor), **payload.model_dump())
    db.add(subject)
    await db.flush()
    await audit(db, actor, "subject.create", "subject", subject.id)
    await db.commit()
    return {"id": subject.id, **payload.model_dump()}


@router.post("/sections/{section_id}/subjects", status_code=201)
async def assign_subject_teacher(section_id: int, payload: SubjectTeacherAssign, db: DbSession, actor: User = Depends(require_roles(*admin_roles))) -> dict:
    school_id = school_id_for(actor)
    section = await db.scalar(select(ClassSection).where(ClassSection.id == section_id, ClassSection.school_id == school_id))
    subject = await db.scalar(select(Subject).where(Subject.id == payload.subject_id, Subject.school_id == school_id))
    teacher = await db.scalar(select(Staff).where(Staff.id == payload.teacher_staff_id, Staff.school_id == school_id, Staff.is_teacher.is_(True)))
    if not section or not subject or not teacher:
        raise HTTPException(status_code=404, detail="Section, subject or teacher not found")
    assignment = ClassSubjectTeacher(school_id=school_id, class_section_id=section_id, subject_id=payload.subject_id, teacher_staff_id=payload.teacher_staff_id)
    db.add(assignment)
    await db.flush()
    await audit(db, actor, "teacher.assign_subject", "class_section", section_id, payload.model_dump())
    await db.commit()
    return {"id": assignment.id, "class_section_id": section_id, **payload.model_dump()}


@router.post("/sections/{section_id}/enrollments", status_code=201)
async def enroll_student(section_id: int, payload: EnrollmentCreate, db: DbSession, actor: User = Depends(require_roles(*admin_roles))) -> dict:
    school_id = school_id_for(actor)
    section = await db.scalar(select(ClassSection).where(ClassSection.id == section_id, ClassSection.school_id == school_id))
    student = await db.scalar(select(Student).where(Student.id == payload.student_id, Student.school_id == school_id))
    year = await db.scalar(select(AcademicYear).where(AcademicYear.id == payload.academic_year_id, AcademicYear.school_id == school_id))
    if not section or not student or not year:
        raise HTTPException(status_code=404, detail="Section, student or academic year not found")
    if section.academic_year_id != payload.academic_year_id:
        raise HTTPException(status_code=400, detail="Section belongs to a different academic year")
    enrollment = Enrollment(school_id=school_id, class_section_id=section_id, **payload.model_dump())
    db.add(enrollment)
    await db.flush()
    await audit(db, actor, "student.enroll", "student", student.id, {"section_id": section_id})
    await db.commit()
    return {"id": enrollment.id, "class_section_id": section_id, **payload.model_dump()}


@router.get("/sections/{section_id}/roster")
async def section_roster(section_id: int, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF, Role.TEACHER))) -> dict:
    school_id = school_id_for(actor)
    section = await db.scalar(select(ClassSection).where(ClassSection.id == section_id, ClassSection.school_id == school_id))
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    rows = (await db.execute(select(Enrollment, Student).join(Student, Student.id == Enrollment.student_id).where(Enrollment.school_id == school_id, Enrollment.class_section_id == section_id, Enrollment.is_active.is_(True)).order_by(Enrollment.roll_no))).all()
    return {"section": {"id": section.id, "grade_name": section.grade_name, "section_name": section.section_name, "classroom_id": section.classroom_id, "class_teacher_staff_id": section.class_teacher_staff_id}, "students": [{"student_id": student.id, "admission_no": student.admission_no, "name": f"{student.first_name} {student.last_name}".strip(), "roll_no": enrollment.roll_no} for enrollment, student in rows]}


@router.get("/students/{student_id}/class")
async def student_class(student_id: int, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF, Role.TEACHER, Role.STUDENT, Role.PARENT, Role.ACCOUNTANT))) -> dict:
    school_id = school_id_for(actor)
    row = (await db.execute(select(Enrollment, ClassSection, Classroom).join(ClassSection, ClassSection.id == Enrollment.class_section_id).outerjoin(Classroom, Classroom.id == ClassSection.classroom_id).where(Enrollment.school_id == school_id, Enrollment.student_id == student_id, Enrollment.is_active.is_(True)).order_by(Enrollment.enrolled_at.desc()).limit(1))).first()
    if not row:
        raise HTTPException(status_code=404, detail="Active class enrollment not found")
    enrollment, section, classroom = row
    subjects = (await db.execute(select(ClassSubjectTeacher, Subject, Staff).join(Subject, Subject.id == ClassSubjectTeacher.subject_id).join(Staff, Staff.id == ClassSubjectTeacher.teacher_staff_id).where(ClassSubjectTeacher.school_id == school_id, ClassSubjectTeacher.class_section_id == section.id))).all()
    return {"student_id": student_id, "academic_year_id": enrollment.academic_year_id, "class": {"id": section.id, "grade": section.grade_name, "section": section.section_name}, "classroom": None if not classroom else {"id": classroom.id, "name": classroom.name, "building": classroom.building, "floor": classroom.floor}, "class_teacher_staff_id": section.class_teacher_staff_id, "subjects": [{"subject_id": subject.id, "subject": subject.name, "code": subject.code, "teacher_staff_id": teacher.id, "teacher": teacher.full_name} for _, subject, teacher in subjects]}


@router.post("/timetable", status_code=201)
async def create_timetable_entry(payload: TimetableCreate, db: DbSession, actor: User = Depends(require_roles(*admin_roles))) -> dict:
    if payload.starts_at >= payload.ends_at:
        raise HTTPException(status_code=400, detail="Timetable start must be before end")
    school_id = school_id_for(actor)
    section = await db.scalar(select(ClassSection).where(ClassSection.id == payload.class_section_id, ClassSection.school_id == school_id))
    teacher = await db.scalar(select(Staff).where(Staff.id == payload.teacher_staff_id, Staff.school_id == school_id, Staff.is_teacher.is_(True)))
    subject = await db.scalar(select(Subject).where(Subject.id == payload.subject_id, Subject.school_id == school_id))
    if not section or not teacher or not subject:
        raise HTTPException(status_code=404, detail="Section, subject or teacher not found")
    entry = TimetableEntry(school_id=school_id, **payload.model_dump())
    db.add(entry)
    await db.flush()
    await audit(db, actor, "timetable.create", "timetable_entry", entry.id)
    await db.commit()
    return {"id": entry.id, **payload.model_dump()}


@router.get("/sections/{section_id}/timetable")
async def section_timetable(section_id: int, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF, Role.TEACHER, Role.STUDENT, Role.PARENT))) -> list[dict]:
    school_id = school_id_for(actor)
    rows = (await db.execute(select(TimetableEntry, Subject, Staff, Classroom).join(Subject, Subject.id == TimetableEntry.subject_id).join(Staff, Staff.id == TimetableEntry.teacher_staff_id).outerjoin(Classroom, Classroom.id == TimetableEntry.classroom_id).where(TimetableEntry.school_id == school_id, TimetableEntry.class_section_id == section_id).order_by(TimetableEntry.weekday, TimetableEntry.starts_at))).all()
    return [{"id": entry.id, "weekday": entry.weekday, "starts_at": entry.starts_at, "ends_at": entry.ends_at, "subject": {"id": subject.id, "name": subject.name, "code": subject.code}, "teacher": {"id": teacher.id, "name": teacher.full_name}, "classroom": None if not room else {"id": room.id, "name": room.name}} for entry, subject, teacher, room in rows]
