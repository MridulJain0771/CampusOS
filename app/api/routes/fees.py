from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select

from app.api.deps import DbSession, require_roles, school_id_for
from app.models.core import User
from app.models.enums import Role
from app.models.fees import FeeStructure, InvoiceLine, Payment, Refund, StudentInvoice
from app.models.people import Student
from app.schemas.fees import FeeStructureCreate, InvoiceCreate, PaymentCreate, RefundCreate
from app.services.audit import audit
from app.services.fees import invoice_total, payment_status, record_payment

router = APIRouter(prefix="/fees", tags=["fees & payments"])
finance_roles = (Role.SCHOOL_ADMIN, Role.ACCOUNTANT)


@router.post("/structures", status_code=201)
async def create_fee_structure(payload: FeeStructureCreate, db: DbSession, actor: User = Depends(require_roles(*finance_roles))) -> dict:
    fee = FeeStructure(school_id=school_id_for(actor), **payload.model_dump())
    db.add(fee)
    await db.flush()
    await audit(db, actor, "fee_structure.create", "fee_structure", fee.id)
    await db.commit()
    return {"id": fee.id, **payload.model_dump()}


@router.get("/structures")
async def list_fee_structures(db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.ACCOUNTANT, Role.PARENT, Role.STUDENT))) -> list[dict]:
    rows = (await db.scalars(select(FeeStructure).where(FeeStructure.school_id == school_id_for(actor)).order_by(FeeStructure.due_date))).all()
    return [{"id": f.id, "academic_year_id": f.academic_year_id, "class_section_id": f.class_section_id, "name": f.name, "category": f.category, "amount": f.amount, "due_date": f.due_date, "late_fee_per_day": f.late_fee_per_day} for f in rows]


@router.post("/invoices", status_code=201)
async def create_invoice(payload: InvoiceCreate, db: DbSession, actor: User = Depends(require_roles(*finance_roles))) -> dict:
    school_id = school_id_for(actor)
    student = await db.scalar(select(Student).where(Student.id == payload.student_id, Student.school_id == school_id))
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    if not payload.lines:
        raise HTTPException(status_code=400, detail="Invoice requires at least one line")
    subtotal = sum((line.amount for line in payload.lines), Decimal("0.00"))
    total = invoice_total(subtotal, payload.discount_amount, payload.late_fee_amount)
    invoice = StudentInvoice(school_id=school_id, academic_year_id=payload.academic_year_id, student_id=payload.student_id, invoice_no=f"INV-{uuid4().hex[:12].upper()}", subtotal=subtotal, discount_amount=payload.discount_amount, late_fee_amount=payload.late_fee_amount, total_amount=total, due_date=payload.due_date)
    db.add(invoice)
    await db.flush()
    for line in payload.lines:
        db.add(InvoiceLine(invoice_id=invoice.id, **line.model_dump()))
    await audit(db, actor, "invoice.create", "student_invoice", invoice.id, {"student_id": student.id, "total": str(total)})
    await db.commit()
    return {"id": invoice.id, "invoice_no": invoice.invoice_no, "student_id": invoice.student_id, "subtotal": invoice.subtotal, "discount_amount": invoice.discount_amount, "late_fee_amount": invoice.late_fee_amount, "total_amount": invoice.total_amount, "paid_amount": invoice.paid_amount, "status": invoice.status, "due_date": invoice.due_date}


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: int, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.ACCOUNTANT, Role.PARENT, Role.STUDENT))) -> dict:
    school_id = school_id_for(actor)
    invoice = await db.scalar(select(StudentInvoice).where(StudentInvoice.id == invoice_id, StudentInvoice.school_id == school_id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    lines = (await db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))).all()
    payments = (await db.scalars(select(Payment).where(Payment.invoice_id == invoice.id).order_by(Payment.paid_at))).all()
    return {"id": invoice.id, "invoice_no": invoice.invoice_no, "student_id": invoice.student_id, "status": invoice.status, "subtotal": invoice.subtotal, "discount_amount": invoice.discount_amount, "late_fee_amount": invoice.late_fee_amount, "total_amount": invoice.total_amount, "paid_amount": invoice.paid_amount, "outstanding_amount": invoice.total_amount - invoice.paid_amount, "due_date": invoice.due_date, "lines": [{"id": l.id, "description": l.description, "amount": l.amount, "fee_structure_id": l.fee_structure_id} for l in lines], "payments": [{"id": p.id, "receipt_no": p.receipt_no, "amount": p.amount, "method": p.method, "reference": p.reference, "paid_at": p.paid_at, "status": p.status} for p in payments]}


@router.get("/students/{student_id}/ledger")
async def student_fee_ledger(student_id: int, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.ACCOUNTANT, Role.PARENT, Role.STUDENT))) -> dict:
    school_id = school_id_for(actor)
    invoices = (await db.scalars(select(StudentInvoice).where(StudentInvoice.school_id == school_id, StudentInvoice.student_id == student_id).order_by(StudentInvoice.created_at.desc()))).all()
    return {"student_id": student_id, "total_billed": sum((i.total_amount for i in invoices), Decimal("0.00")), "total_paid": sum((i.paid_amount for i in invoices), Decimal("0.00")), "outstanding": sum((i.total_amount - i.paid_amount for i in invoices), Decimal("0.00")), "invoices": [{"id": i.id, "invoice_no": i.invoice_no, "status": i.status, "total": i.total_amount, "paid": i.paid_amount, "due_date": i.due_date} for i in invoices]}


@router.post("/invoices/{invoice_id}/payments", status_code=201)
async def pay_invoice(invoice_id: int, payload: PaymentCreate, db: DbSession, response: Response, actor: User = Depends(require_roles(*finance_roles)), idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    school_id = school_id_for(actor)
    invoice = await db.scalar(select(StudentInvoice).where(StudentInvoice.id == invoice_id, StudentInvoice.school_id == school_id).with_for_update())
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    try:
        payment, replay = await record_payment(db, school_id=school_id, invoice=invoice, idempotency_key=idempotency_key, amount=payload.amount, method=payload.method, reference=payload.reference)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not replay:
        await audit(db, actor, "payment.record", "payment", payment.id, {"invoice_id": invoice.id, "amount": str(payment.amount)})
        await db.commit()
    else:
        response.status_code = 200
        response.headers["X-Idempotent-Replay"] = "true"
    return {"id": payment.id, "receipt_no": payment.receipt_no, "invoice_id": payment.invoice_id, "amount": payment.amount, "method": payment.method, "status": payment.status, "replay": replay}


@router.post("/payments/{payment_id}/refunds", status_code=201)
async def refund_payment(payment_id: int, payload: RefundCreate, db: DbSession, actor: User = Depends(require_roles(*finance_roles))) -> dict:
    school_id = school_id_for(actor)
    payment = await db.scalar(select(Payment).where(Payment.id == payment_id, Payment.school_id == school_id).with_for_update())
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    previous = sum((r.amount for r in (await db.scalars(select(Refund).where(Refund.payment_id == payment.id))).all()), Decimal("0.00"))
    if previous + payload.amount > payment.amount:
        raise HTTPException(status_code=400, detail="Refund exceeds paid amount")
    invoice = await db.scalar(select(StudentInvoice).where(StudentInvoice.id == payment.invoice_id).with_for_update())
    refund = Refund(school_id=school_id, payment_id=payment.id, **payload.model_dump())
    db.add(refund)
    invoice.paid_amount -= payload.amount
    invoice.status = payment_status(invoice.total_amount, invoice.paid_amount)
    if previous + payload.amount == payment.amount:
        payment.status = "refunded"
    await db.flush()
    await audit(db, actor, "payment.refund", "refund", refund.id, {"payment_id": payment.id, "amount": str(refund.amount)})
    await db.commit()
    return {"id": refund.id, "payment_id": payment.id, "amount": refund.amount, "reason": refund.reason}
