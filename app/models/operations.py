from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LifecycleEvent(Base):
    __tablename__ = "lifecycle_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(20), index=True)
    entity_id: Mapped[int] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    effective_on: Mapped[date] = mapped_column(Date, index=True)
    reason: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentRecord(Base):
    __tablename__ = "document_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    owner_type: Mapped[str] = mapped_column(String(30), index=True)
    owner_id: Mapped[int | None] = mapped_column(index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(200))
    storage_url: Mapped[str] = mapped_column(String(1000))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    issued_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    is_important: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Exam(Base):
    __tablename__ = "exams"
    __table_args__ = (
        UniqueConstraint("school_id", "academic_year_id", "name", "class_section_id", name="uq_exam_school_year_class_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    academic_year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id", ondelete="CASCADE"), index=True)
    class_section_id: Mapped[int | None] = mapped_column(ForeignKey("class_sections.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(140))
    term: Mapped[str | None] = mapped_column(String(80))
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExamScore(Base):
    __tablename__ = "exam_scores"
    __table_args__ = (UniqueConstraint("exam_id", "student_id", "subject_id", name="uq_exam_student_subject_score"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    marks_obtained: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    max_marks: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    grade: Mapped[str | None] = mapped_column(String(20))
    remarks: Mapped[str | None] = mapped_column(String(500))
    recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ReportCard(Base):
    __tablename__ = "report_cards"
    __table_args__ = (UniqueConstraint("exam_id", "student_id", name="uq_report_card_exam_student"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    total_marks: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    max_total_marks: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    percentage: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    overall_grade: Mapped[str] = mapped_column(String(20))
    teacher_remarks: Mapped[str | None] = mapped_column(Text)
    published_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SalaryStructure(Base):
    __tablename__ = "salary_structures"

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"), index=True)
    basic_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    allowances: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    standard_deductions: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (UniqueConstraint("school_id", "year", "month", name="uq_payroll_school_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    generated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PayrollItem(Base):
    __tablename__ = "payroll_items"
    __table_args__ = (UniqueConstraint("payroll_run_id", "staff_id", name="uq_payroll_run_staff"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    payroll_run_id: Mapped[int] = mapped_column(ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="RESTRICT"), index=True)
    salary_structure_id: Mapped[int | None] = mapped_column(ForeignKey("salary_structures.id", ondelete="SET NULL"))
    basic_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    allowances: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    deductions: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    gross_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    net_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_method: Mapped[str | None] = mapped_column(String(40))
    payment_reference: Mapped[str | None] = mapped_column(String(120))


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    __table_args__ = (UniqueConstraint("school_id", "name", name="uq_expense_category_school"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("expense_categories.id", ondelete="SET NULL"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    incurred_on: Mapped[date] = mapped_column(Date, index=True)
    vendor: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    payment_method: Mapped[str | None] = mapped_column(String(40))
    reference: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="paid", index=True)
    recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
