from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import DbSession, require_roles, school_id_for
from app.models.academics import ClassSection
from app.models.core import User
from app.models.enums import Role
from app.models.fees import Payment, StudentInvoice
from app.models.people import Staff, Student

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard(db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.ACCOUNTANT, Role.STAFF))) -> dict:
    school_id = school_id_for(actor)
    student_count = await db.scalar(select(func.count(Student.id)).where(Student.school_id == school_id, Student.is_active.is_(True))) or 0
    staff_count = await db.scalar(select(func.count(Staff.id)).where(Staff.school_id == school_id, Staff.is_active.is_(True))) or 0
    section_count = await db.scalar(select(func.count(ClassSection.id)).where(ClassSection.school_id == school_id)) or 0
    billed = await db.scalar(select(func.coalesce(func.sum(StudentInvoice.total_amount), 0)).where(StudentInvoice.school_id == school_id)) or Decimal("0.00")
    paid = await db.scalar(select(func.coalesce(func.sum(StudentInvoice.paid_amount), 0)).where(StudentInvoice.school_id == school_id)) or Decimal("0.00")
    payment_count = await db.scalar(select(func.count(Payment.id)).where(Payment.school_id == school_id)) or 0
    return {"students": student_count, "staff": staff_count, "class_sections": section_count, "fees": {"billed": billed, "paid": paid, "outstanding": billed - paid, "payments_recorded": payment_count}}
