from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class LifecycleChange(BaseModel):
    effective_on: date
    reason: str | None = Field(default=None, max_length=200)
    notes: str | None = None


class DocumentCreate(BaseModel):
    owner_type: Literal["student", "staff", "school"]
    owner_id: int | None = None
    category: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=200)
    storage_url: str = Field(min_length=4, max_length=1000)
    mime_type: str | None = Field(default=None, max_length=120)
    issued_on: date | None = None
    expires_on: date | None = None
    is_important: bool = False
    metadata_json: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_owner(self):
        if self.owner_type != "school" and self.owner_id is None:
            raise ValueError("owner_id is required for student/staff documents")
        return self


class ExamCreate(BaseModel):
    academic_year_id: int
    class_section_id: int | None = None
    name: str = Field(min_length=2, max_length=140)
    term: str | None = Field(default=None, max_length=80)
    starts_on: date | None = None
    ends_on: date | None = None


class ExamScoreUpsert(BaseModel):
    student_id: int
    subject_id: int
    marks_obtained: Decimal = Field(ge=0)
    max_marks: Decimal = Field(gt=0)
    grade: str | None = Field(default=None, max_length=20)
    remarks: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_marks(self):
        if self.marks_obtained > self.max_marks:
            raise ValueError("marks_obtained cannot exceed max_marks")
        return self


class PublishReportCard(BaseModel):
    teacher_remarks: str | None = None


class SalaryStructureCreate(BaseModel):
    staff_id: int
    basic_salary: Decimal = Field(gt=0)
    allowances: Decimal = Field(default=Decimal("0.00"), ge=0)
    standard_deductions: Decimal = Field(default=Decimal("0.00"), ge=0)
    effective_from: date

    @model_validator(mode="after")
    def validate_net_salary(self):
        if self.standard_deductions > self.basic_salary + self.allowances:
            raise ValueError("standard_deductions cannot exceed gross salary")
        return self


class PayrollRunCreate(BaseModel):
    year: int = Field(ge=2000, le=2200)
    month: int = Field(ge=1, le=12)


class PayrollPayment(BaseModel):
    payment_method: str = Field(min_length=2, max_length=40)
    payment_reference: str | None = Field(default=None, max_length=120)


class ExpenseCategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class ExpenseCreate(BaseModel):
    category_id: int | None = None
    amount: Decimal = Field(gt=0)
    incurred_on: date
    vendor: str | None = Field(default=None, max_length=200)
    description: str = Field(min_length=2)
    payment_method: str | None = Field(default=None, max_length=40)
    reference: str | None = Field(default=None, max_length=120)
    status: Literal["pending", "paid", "cancelled"] = "paid"
