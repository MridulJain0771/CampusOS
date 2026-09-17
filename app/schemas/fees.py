from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class FeeStructureCreate(BaseModel):
    academic_year_id: int
    class_section_id: int | None = None
    name: str
    category: str = "tuition"
    amount: Decimal = Field(gt=0)
    due_date: date
    late_fee_per_day: Decimal = Field(default=Decimal("0.00"), ge=0)


class InvoiceLineCreate(BaseModel):
    fee_structure_id: int | None = None
    description: str
    amount: Decimal = Field(gt=0)


class InvoiceCreate(BaseModel):
    academic_year_id: int
    student_id: int
    due_date: date
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    late_fee_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    lines: list[InvoiceLineCreate]


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str
    reference: str | None = None


class RefundCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    reason: str
