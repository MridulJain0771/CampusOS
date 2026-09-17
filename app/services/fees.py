from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import InvoiceStatus
from app.models.fees import Payment, StudentInvoice


def invoice_total(subtotal: Decimal, discount: Decimal, late_fee: Decimal) -> Decimal:
    return max(Decimal("0.00"), subtotal - discount + late_fee)


def payment_status(total: Decimal, paid: Decimal) -> str:
    if paid <= 0:
        return InvoiceStatus.OPEN.value
    if paid >= total:
        return InvoiceStatus.PAID.value
    return InvoiceStatus.PARTIAL.value


async def record_payment(
    db: AsyncSession,
    *,
    school_id: int,
    invoice: StudentInvoice,
    idempotency_key: str,
    amount: Decimal,
    method: str,
    reference: str | None,
) -> tuple[Payment, bool]:
    existing = await db.scalar(
        select(Payment).where(
            Payment.school_id == school_id,
            Payment.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing, True

    outstanding = invoice.total_amount - invoice.paid_amount
    if amount > outstanding:
        raise ValueError("Payment exceeds invoice outstanding amount")

    payment = Payment(
        school_id=school_id,
        invoice_id=invoice.id,
        student_id=invoice.student_id,
        receipt_no=f"RCPT-{uuid4().hex[:12].upper()}",
        idempotency_key=idempotency_key,
        amount=amount,
        method=method,
        reference=reference,
    )
    invoice.paid_amount += amount
    invoice.status = payment_status(invoice.total_amount, invoice.paid_amount)
    db.add(payment)
    try:
        await db.flush()
        return payment, False
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(Payment).where(
                Payment.school_id == school_id,
                Payment.idempotency_key == idempotency_key,
            )
        )
        if existing:
            return existing, True
        raise
