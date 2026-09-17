from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from app.api.deps import DbSession, require_roles, school_id_for
from app.models.core import User
from app.models.enums import Role
from app.models.fees import Payment, Refund
from app.models.operations import Expense, ExpenseCategory, PayrollItem, PayrollRun, SalaryStructure
from app.models.people import Staff
from app.schemas.operations import ExpenseCategoryCreate, ExpenseCreate, PayrollPayment, PayrollRunCreate, SalaryStructureCreate
from app.services.audit import audit

router = APIRouter(prefix="/finance", tags=["staff payroll & expenditure"])
finance_roles = (Role.SCHOOL_ADMIN, Role.ACCOUNTANT)


@router.post("/salary-structures", status_code=201)
async def create_salary_structure(
    payload: SalaryStructureCreate,
    db: DbSession,
    actor: User = Depends(require_roles(*finance_roles)),
) -> dict:
    school_id = school_id_for(actor)
    staff = await db.scalar(
        select(Staff).where(Staff.id == payload.staff_id, Staff.school_id == school_id)
    )
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    previous = (
        await db.scalars(
            select(SalaryStructure).where(
                SalaryStructure.school_id == school_id,
                SalaryStructure.staff_id == payload.staff_id,
                SalaryStructure.is_active.is_(True),
            )
        )
    ).all()
    for row in previous:
        row.is_active = False
    salary = SalaryStructure(school_id=school_id, **payload.model_dump())
    db.add(salary)
    await db.flush()
    await audit(
        db,
        actor,
        "salary_structure.create",
        "salary_structure",
        salary.id,
        {"staff_id": salary.staff_id},
    )
    await db.commit()
    gross = salary.basic_salary + salary.allowances
    return {
        "id": salary.id,
        "staff_id": salary.staff_id,
        "basic_salary": salary.basic_salary,
        "allowances": salary.allowances,
        "deductions": salary.standard_deductions,
        "gross_salary": gross,
        "net_salary": gross - salary.standard_deductions,
        "effective_from": salary.effective_from,
    }


@router.get("/staff/{staff_id}/salary-structures")
async def salary_history(
    staff_id: int,
    db: DbSession,
    actor: User = Depends(require_roles(*finance_roles)),
) -> list[dict]:
    rows = (
        await db.scalars(
            select(SalaryStructure)
            .where(
                SalaryStructure.school_id == school_id_for(actor),
                SalaryStructure.staff_id == staff_id,
            )
            .order_by(SalaryStructure.effective_from.desc())
        )
    ).all()
    return [
        {
            "id": s.id,
            "basic_salary": s.basic_salary,
            "allowances": s.allowances,
            "deductions": s.standard_deductions,
            "effective_from": s.effective_from,
            "is_active": s.is_active,
        }
        for s in rows
    ]


@router.post("/payroll-runs", status_code=201)
async def create_payroll_run(
    payload: PayrollRunCreate,
    db: DbSession,
    actor: User = Depends(require_roles(*finance_roles)),
) -> dict:
    school_id = school_id_for(actor)
    existing = await db.scalar(
        select(PayrollRun).where(
            PayrollRun.school_id == school_id,
            PayrollRun.year == payload.year,
            PayrollRun.month == payload.month,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Payroll run already exists for this month")
    run = PayrollRun(
        school_id=school_id,
        generated_by_user_id=actor.id,
        **payload.model_dump(),
    )
    db.add(run)
    await db.flush()
    await audit(
        db,
        actor,
        "payroll_run.create",
        "payroll_run",
        run.id,
        payload.model_dump(),
    )
    await db.commit()
    return {"id": run.id, "year": run.year, "month": run.month, "status": run.status}


@router.post("/payroll-runs/{run_id}/generate")
async def generate_payroll(
    run_id: int,
    db: DbSession,
    actor: User = Depends(require_roles(*finance_roles)),
) -> dict:
    school_id = school_id_for(actor)
    run = await db.scalar(
        select(PayrollRun).where(PayrollRun.id == run_id, PayrollRun.school_id == school_id)
    )
    if not run:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    existing_items = (
        await db.scalars(select(PayrollItem).where(PayrollItem.payroll_run_id == run_id))
    ).all()
    if existing_items:
        return {
            "run_id": run.id,
            "generated": len(existing_items),
            "status": run.status,
            "replay": True,
        }
    staff_members = (
        await db.scalars(
            select(Staff)
            .where(Staff.school_id == school_id, Staff.is_active.is_(True))
            .order_by(Staff.id)
        )
    ).all()
    generated = 0
    for staff in staff_members:
        salary = await db.scalar(
            select(SalaryStructure)
            .where(
                SalaryStructure.school_id == school_id,
                SalaryStructure.staff_id == staff.id,
                SalaryStructure.is_active.is_(True),
            )
            .order_by(SalaryStructure.effective_from.desc())
            .limit(1)
        )
        if not salary:
            continue
        gross = salary.basic_salary + salary.allowances
        net = gross - salary.standard_deductions
        db.add(
            PayrollItem(
                school_id=school_id,
                payroll_run_id=run.id,
                staff_id=staff.id,
                salary_structure_id=salary.id,
                basic_salary=salary.basic_salary,
                allowances=salary.allowances,
                deductions=salary.standard_deductions,
                gross_salary=gross,
                net_salary=net,
            )
        )
        generated += 1
    run.status = "generated"
    await audit(
        db,
        actor,
        "payroll_run.generate",
        "payroll_run",
        run.id,
        {"generated_items": generated},
    )
    await db.commit()
    return {"run_id": run.id, "generated": generated, "status": run.status, "replay": False}


@router.get("/payroll-runs/{run_id}")
async def get_payroll_run(
    run_id: int,
    db: DbSession,
    actor: User = Depends(require_roles(*finance_roles)),
) -> dict:
    school_id = school_id_for(actor)
    run = await db.scalar(
        select(PayrollRun).where(PayrollRun.id == run_id, PayrollRun.school_id == school_id)
    )
    if not run:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    items = (
        await db.scalars(
            select(PayrollItem)
            .where(PayrollItem.payroll_run_id == run_id)
            .order_by(PayrollItem.staff_id)
        )
    ).all()
    return {
        "id": run.id,
        "year": run.year,
        "month": run.month,
        "status": run.status,
        "gross_total": sum((i.gross_salary for i in items), Decimal("0.00")),
        "net_total": sum((i.net_salary for i in items), Decimal("0.00")),
        "paid_total": sum(
            (i.net_salary for i in items if i.status == "paid"), Decimal("0.00")
        ),
        "items": [
            {
                "id": i.id,
                "staff_id": i.staff_id,
                "gross_salary": i.gross_salary,
                "deductions": i.deductions,
                "net_salary": i.net_salary,
                "status": i.status,
                "paid_at": i.paid_at,
                "payment_reference": i.payment_reference,
            }
            for i in items
        ],
    }


@router.post("/payroll-items/{item_id}/pay")
async def pay_staff_salary(
    item_id: int,
    payload: PayrollPayment,
    db: DbSession,
    actor: User = Depends(require_roles(*finance_roles)),
) -> dict:
    school_id = school_id_for(actor)
    item = await db.scalar(
        select(PayrollItem)
        .where(PayrollItem.id == item_id, PayrollItem.school_id == school_id)
        .with_for_update()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Payroll item not found")
    if item.status == "paid":
        return {
            "id": item.id,
            "staff_id": item.staff_id,
            "net_salary": item.net_salary,
            "status": item.status,
            "paid_at": item.paid_at,
            "payment_reference": item.payment_reference,
            "replay": True,
        }
    item.status = "paid"
    item.paid_at = datetime.now(UTC)
    item.payment_method = payload.payment_method
    item.payment_reference = payload.payment_reference
    await db.flush()
    pending_count = await db.scalar(
        select(func.count(PayrollItem.id)).where(
            PayrollItem.payroll_run_id == item.payroll_run_id,
            PayrollItem.status != "paid",
        )
    )
    if pending_count == 0:
        run = await db.scalar(select(PayrollRun).where(PayrollRun.id == item.payroll_run_id))
        if run:
            run.status = "paid"
    await audit(
        db,
        actor,
        "payroll_item.pay",
        "payroll_item",
        item.id,
        {"staff_id": item.staff_id, "amount": str(item.net_salary)},
    )
    await db.commit()
    return {
        "id": item.id,
        "staff_id": item.staff_id,
        "net_salary": item.net_salary,
        "status": item.status,
        "paid_at": item.paid_at,
        "payment_reference": item.payment_reference,
        "replay": False,
    }


@router.post("/expense-categories", status_code=201)
async def create_expense_category(
    payload: ExpenseCategoryCreate,
    db: DbSession,
    actor: User = Depends(require_roles(*finance_roles)),
) -> dict:
    category = ExpenseCategory(school_id=school_id_for(actor), **payload.model_dump())
    db.add(category)
    await db.flush()
    await audit(db, actor, "expense_category.create", "expense_category", category.id)
    await db.commit()
    return {"id": category.id, "name": category.name, "description": category.description}


@router.post("/expenses", status_code=201)
async def create_expense(
    payload: ExpenseCreate,
    db: DbSession,
    actor: User = Depends(require_roles(*finance_roles)),
) -> dict:
    school_id = school_id_for(actor)
    if payload.category_id is not None:
        category = await db.scalar(
            select(ExpenseCategory).where(
                ExpenseCategory.id == payload.category_id,
                ExpenseCategory.school_id == school_id,
            )
        )
        if not category:
            raise HTTPException(status_code=404, detail="Expense category not found")
    expense = Expense(
        school_id=school_id,
        recorded_by_user_id=actor.id,
        **payload.model_dump(),
    )
    db.add(expense)
    await db.flush()
    await audit(
        db,
        actor,
        "expense.create",
        "expense",
        expense.id,
        {"amount": str(expense.amount), "category_id": expense.category_id},
    )
    await db.commit()
    return {
        "id": expense.id,
        "category_id": expense.category_id,
        "amount": expense.amount,
        "incurred_on": expense.incurred_on,
        "vendor": expense.vendor,
        "description": expense.description,
        "status": expense.status,
    }


@router.get("/expenses")
async def list_expenses(
    db: DbSession,
    actor: User = Depends(require_roles(*finance_roles)),
) -> list[dict]:
    rows = (
        await db.scalars(
            select(Expense)
            .where(Expense.school_id == school_id_for(actor))
            .order_by(Expense.incurred_on.desc(), Expense.id.desc())
        )
    ).all()
    return [
        {
            "id": e.id,
            "category_id": e.category_id,
            "amount": e.amount,
            "incurred_on": e.incurred_on,
            "vendor": e.vendor,
            "description": e.description,
            "payment_method": e.payment_method,
            "reference": e.reference,
            "status": e.status,
        }
        for e in rows
    ]


@router.get("/summary")
async def finance_summary(
    db: DbSession,
    actor: User = Depends(require_roles(*finance_roles)),
) -> dict:
    school_id = school_id_for(actor)
    fee_collections = await db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.school_id == school_id,
            Payment.status == "success",
        )
    )
    refunds = await db.scalar(
        select(func.coalesce(func.sum(Refund.amount), 0)).where(Refund.school_id == school_id)
    )
    payroll_paid = await db.scalar(
        select(func.coalesce(func.sum(PayrollItem.net_salary), 0)).where(
            PayrollItem.school_id == school_id,
            PayrollItem.status == "paid",
        )
    )
    expenses_paid = await db.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.school_id == school_id,
            Expense.status == "paid",
        )
    )
    net_fee_collections = Decimal(str(fee_collections)) - Decimal(str(refunds))
    total_outflow = Decimal(str(payroll_paid)) + Decimal(str(expenses_paid))
    return {
        "fee_collections": net_fee_collections,
        "payroll_paid": payroll_paid,
        "other_expenditure": expenses_paid,
        "total_outflow": total_outflow,
        "operating_net": net_fee_collections - total_outflow,
    }
