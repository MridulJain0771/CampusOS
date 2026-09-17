from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select

from app.api.deps import DbSession, require_roles, school_id_for
from app.models.academics import ClassSection, Subject
from app.models.core import User
from app.models.enums import Role
from app.models.operations import DocumentRecord, Exam, ExamScore, ReportCard
from app.models.people import Parent, Staff, Student, StudentParent
from app.schemas.operations import DocumentCreate, ExamCreate, ExamScoreUpsert, PublishReportCard
from app.services.audit import audit
from app.services.reports import grade_for_percentage

router = APIRouter(prefix="/reports", tags=["documents, exams & report cards"])
report_roles = (Role.SCHOOL_ADMIN, Role.TEACHER, Role.STAFF)


async def _student_ids_for_actor(db: DbSession, actor: User) -> list[int] | None:
    if actor.role in {Role.SCHOOL_ADMIN.value, Role.TEACHER.value, Role.STAFF.value}:
        return None
    if actor.role == Role.STUDENT.value:
        student_id = await db.scalar(
            select(Student.id).where(
                Student.school_id == school_id_for(actor),
                Student.user_id == actor.id,
            )
        )
        return [student_id] if student_id else []
    if actor.role == Role.PARENT.value:
        parent_id = await db.scalar(
            select(Parent.id).where(
                Parent.school_id == school_id_for(actor),
                Parent.user_id == actor.id,
            )
        )
        if not parent_id:
            return []
        return list(
            (
                await db.scalars(
                    select(StudentParent.student_id).where(
                        StudentParent.school_id == school_id_for(actor),
                        StudentParent.parent_id == parent_id,
                    )
                )
            ).all()
        )
    return []


async def _assert_student_access(db: DbSession, actor: User, student_id: int) -> None:
    allowed_ids = await _student_ids_for_actor(db, actor)
    if allowed_ids is not None and student_id not in allowed_ids:
        raise HTTPException(status_code=403, detail="Student report access denied")


@router.post("/documents", status_code=201)
async def create_document(
    payload: DocumentCreate,
    db: DbSession,
    actor: User = Depends(require_roles(*report_roles)),
) -> dict:
    school_id = school_id_for(actor)
    if payload.owner_type == "student":
        owner = await db.scalar(
            select(Student).where(Student.id == payload.owner_id, Student.school_id == school_id)
        )
        if not owner:
            raise HTTPException(status_code=404, detail="Student not found")
    elif payload.owner_type == "staff":
        owner = await db.scalar(
            select(Staff).where(Staff.id == payload.owner_id, Staff.school_id == school_id)
        )
        if not owner:
            raise HTTPException(status_code=404, detail="Staff member not found")
    document = DocumentRecord(
        school_id=school_id,
        uploaded_by_user_id=actor.id,
        **payload.model_dump(),
    )
    db.add(document)
    await db.flush()
    await audit(
        db,
        actor,
        "document.create",
        "document",
        document.id,
        {
            "owner_type": document.owner_type,
            "owner_id": document.owner_id,
            "category": document.category,
        },
    )
    await db.commit()
    return {
        "id": document.id,
        "owner_type": document.owner_type,
        "owner_id": document.owner_id,
        "category": document.category,
        "title": document.title,
        "storage_url": document.storage_url,
        "is_important": document.is_important,
        "expires_on": document.expires_on,
    }


@router.get("/documents")
async def list_documents(
    db: DbSession,
    actor: User = Depends(
        require_roles(
            Role.SCHOOL_ADMIN,
            Role.TEACHER,
            Role.STAFF,
            Role.STUDENT,
            Role.PARENT,
        )
    ),
    owner_type: str | None = Query(default=None),
    owner_id: int | None = Query(default=None),
    important_only: bool = Query(default=False),
) -> list[dict]:
    school_id = school_id_for(actor)
    query = select(DocumentRecord).where(DocumentRecord.school_id == school_id)
    allowed_student_ids = await _student_ids_for_actor(db, actor)
    if allowed_student_ids is not None:
        query = query.where(
            or_(
                DocumentRecord.owner_type == "school",
                (DocumentRecord.owner_type == "student")
                & DocumentRecord.owner_id.in_(allowed_student_ids),
            )
        )
    if owner_type:
        query = query.where(DocumentRecord.owner_type == owner_type)
    if owner_id is not None:
        if (
            allowed_student_ids is not None
            and owner_type == "student"
            and owner_id not in allowed_student_ids
        ):
            raise HTTPException(status_code=403, detail="Document access denied")
        query = query.where(DocumentRecord.owner_id == owner_id)
    if important_only:
        query = query.where(DocumentRecord.is_important.is_(True))
    rows = (await db.scalars(query.order_by(DocumentRecord.created_at.desc()))).all()
    return [
        {
            "id": d.id,
            "owner_type": d.owner_type,
            "owner_id": d.owner_id,
            "category": d.category,
            "title": d.title,
            "storage_url": d.storage_url,
            "mime_type": d.mime_type,
            "issued_on": d.issued_on,
            "expires_on": d.expires_on,
            "is_important": d.is_important,
            "metadata": d.metadata_json,
        }
        for d in rows
    ]


@router.post("/exams", status_code=201)
async def create_exam(
    payload: ExamCreate,
    db: DbSession,
    actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.TEACHER)),
) -> dict:
    school_id = school_id_for(actor)
    if payload.class_section_id is not None:
        section = await db.scalar(
            select(ClassSection).where(
                ClassSection.id == payload.class_section_id,
                ClassSection.school_id == school_id,
            )
        )
        if not section:
            raise HTTPException(status_code=404, detail="Class section not found")
    exam = Exam(school_id=school_id, **payload.model_dump())
    db.add(exam)
    await db.flush()
    await audit(db, actor, "exam.create", "exam", exam.id, {"name": exam.name})
    await db.commit()
    return {
        "id": exam.id,
        "name": exam.name,
        "term": exam.term,
        "academic_year_id": exam.academic_year_id,
        "class_section_id": exam.class_section_id,
        "is_published": exam.is_published,
    }


@router.put("/exams/{exam_id}/scores")
async def upsert_exam_score(
    exam_id: int,
    payload: ExamScoreUpsert,
    db: DbSession,
    actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.TEACHER)),
) -> dict:
    school_id = school_id_for(actor)
    exam = await db.scalar(
        select(Exam).where(Exam.id == exam_id, Exam.school_id == school_id)
    )
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    student = await db.scalar(
        select(Student).where(
            Student.id == payload.student_id,
            Student.school_id == school_id,
        )
    )
    subject = await db.scalar(
        select(Subject).where(
            Subject.id == payload.subject_id,
            Subject.school_id == school_id,
        )
    )
    if not student or not subject:
        raise HTTPException(status_code=404, detail="Student or subject not found")
    score = await db.scalar(
        select(ExamScore).where(
            ExamScore.exam_id == exam_id,
            ExamScore.student_id == payload.student_id,
            ExamScore.subject_id == payload.subject_id,
        )
    )
    if score:
        for key, value in payload.model_dump().items():
            setattr(score, key, value)
        score.recorded_by_user_id = actor.id
    else:
        score = ExamScore(
            school_id=school_id,
            exam_id=exam_id,
            recorded_by_user_id=actor.id,
            **payload.model_dump(),
        )
        db.add(score)
    await db.flush()
    await audit(
        db,
        actor,
        "exam_score.upsert",
        "exam_score",
        score.id,
        {
            "exam_id": exam_id,
            "student_id": payload.student_id,
            "subject_id": payload.subject_id,
        },
    )
    await db.commit()
    pct = (
        score.marks_obtained / score.max_marks * Decimal("100")
        if score.max_marks
        else Decimal("0")
    )
    return {
        "id": score.id,
        "exam_id": exam_id,
        "student_id": score.student_id,
        "subject_id": score.subject_id,
        "marks_obtained": score.marks_obtained,
        "max_marks": score.max_marks,
        "percentage": pct.quantize(Decimal("0.01")),
        "grade": score.grade or grade_for_percentage(pct),
    }


async def _score_rows(
    db: DbSession,
    school_id: int,
    exam_id: int,
    student_id: int,
) -> list[ExamScore]:
    return (
        await db.scalars(
            select(ExamScore)
            .where(
                ExamScore.school_id == school_id,
                ExamScore.exam_id == exam_id,
                ExamScore.student_id == student_id,
            )
            .order_by(ExamScore.subject_id)
        )
    ).all()


@router.get("/exams/{exam_id}/students/{student_id}/report-card")
async def preview_report_card(
    exam_id: int,
    student_id: int,
    db: DbSession,
    actor: User = Depends(
        require_roles(
            Role.SCHOOL_ADMIN,
            Role.TEACHER,
            Role.STAFF,
            Role.STUDENT,
            Role.PARENT,
        )
    ),
) -> dict:
    school_id = school_id_for(actor)
    await _assert_student_access(db, actor, student_id)
    exam = await db.scalar(
        select(Exam).where(Exam.id == exam_id, Exam.school_id == school_id)
    )
    student = await db.scalar(
        select(Student).where(Student.id == student_id, Student.school_id == school_id)
    )
    if not exam or not student:
        raise HTTPException(status_code=404, detail="Exam or student not found")
    scores = await _score_rows(db, school_id, exam_id, student_id)
    if not scores:
        raise HTTPException(status_code=404, detail="No scores recorded")
    total = sum((s.marks_obtained for s in scores), Decimal("0.00"))
    max_total = sum((s.max_marks for s in scores), Decimal("0.00"))
    percentage = (
        total / max_total * Decimal("100") if max_total else Decimal("0")
    )
    subjects = []
    for score in scores:
        subject = await db.scalar(select(Subject).where(Subject.id == score.subject_id))
        subject_pct = score.marks_obtained / score.max_marks * Decimal("100")
        subjects.append(
            {
                "subject_id": score.subject_id,
                "subject": subject.name if subject else None,
                "marks": score.marks_obtained,
                "max_marks": score.max_marks,
                "grade": score.grade or grade_for_percentage(subject_pct),
                "remarks": score.remarks,
            }
        )
    published = await db.scalar(
        select(ReportCard).where(
            ReportCard.exam_id == exam_id,
            ReportCard.student_id == student_id,
        )
    )
    return {
        "exam": {"id": exam.id, "name": exam.name, "term": exam.term},
        "student": {
            "id": student.id,
            "admission_no": student.admission_no,
            "name": f"{student.first_name} {student.last_name}".strip(),
        },
        "subjects": subjects,
        "total_marks": total,
        "max_total_marks": max_total,
        "percentage": percentage.quantize(Decimal("0.01")),
        "overall_grade": grade_for_percentage(percentage),
        "published": published is not None,
        "teacher_remarks": published.teacher_remarks if published else None,
    }


@router.post("/exams/{exam_id}/students/{student_id}/publish", status_code=201)
async def publish_report_card(
    exam_id: int,
    student_id: int,
    payload: PublishReportCard,
    db: DbSession,
    actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.TEACHER)),
) -> dict:
    school_id = school_id_for(actor)
    exam = await db.scalar(
        select(Exam).where(Exam.id == exam_id, Exam.school_id == school_id)
    )
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    scores = await _score_rows(db, school_id, exam_id, student_id)
    if not scores:
        raise HTTPException(status_code=400, detail="Cannot publish without exam scores")
    total = sum((s.marks_obtained for s in scores), Decimal("0.00"))
    max_total = sum((s.max_marks for s in scores), Decimal("0.00"))
    percentage = (
        total / max_total * Decimal("100") if max_total else Decimal("0")
    )
    card = await db.scalar(
        select(ReportCard).where(
            ReportCard.exam_id == exam_id,
            ReportCard.student_id == student_id,
        )
    )
    if not card:
        card = ReportCard(
            school_id=school_id,
            exam_id=exam_id,
            student_id=student_id,
            total_marks=total,
            max_total_marks=max_total,
            percentage=percentage,
            overall_grade=grade_for_percentage(percentage),
            teacher_remarks=payload.teacher_remarks,
            published_by_user_id=actor.id,
        )
        db.add(card)
    else:
        card.total_marks = total
        card.max_total_marks = max_total
        card.percentage = percentage
        card.overall_grade = grade_for_percentage(percentage)
        card.teacher_remarks = payload.teacher_remarks
        card.published_by_user_id = actor.id
    exam.is_published = True
    await db.flush()
    await audit(
        db,
        actor,
        "report_card.publish",
        "report_card",
        card.id,
        {"exam_id": exam_id, "student_id": student_id},
    )
    await db.commit()
    return {
        "id": card.id,
        "exam_id": exam_id,
        "student_id": student_id,
        "total_marks": card.total_marks,
        "max_total_marks": card.max_total_marks,
        "percentage": card.percentage,
        "overall_grade": card.overall_grade,
        "teacher_remarks": card.teacher_remarks,
        "published_at": card.published_at,
    }


@router.get("/students/{student_id}/report-cards")
async def list_report_cards(
    student_id: int,
    db: DbSession,
    actor: User = Depends(
        require_roles(
            Role.SCHOOL_ADMIN,
            Role.TEACHER,
            Role.STAFF,
            Role.STUDENT,
            Role.PARENT,
        )
    ),
) -> list[dict]:
    await _assert_student_access(db, actor, student_id)
    rows = (
        await db.scalars(
            select(ReportCard)
            .where(
                ReportCard.school_id == school_id_for(actor),
                ReportCard.student_id == student_id,
            )
            .order_by(ReportCard.published_at.desc())
        )
    ).all()
    return [
        {
            "id": c.id,
            "exam_id": c.exam_id,
            "percentage": c.percentage,
            "overall_grade": c.overall_grade,
            "teacher_remarks": c.teacher_remarks,
            "published_at": c.published_at,
        }
        for c in rows
    ]
