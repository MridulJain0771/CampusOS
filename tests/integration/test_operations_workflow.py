import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
def test_lifecycle_reports_and_finance_workflow():
    suffix = uuid.uuid4().hex[:8]
    assert settings.bootstrap_superadmin_email
    assert settings.bootstrap_superadmin_password

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": settings.bootstrap_superadmin_email,
                "password": settings.bootstrap_superadmin_password,
            },
        )
        assert login.status_code == 200

        admin_email = f"ops-{suffix}@example.com"
        school = client.post(
            "/api/v1/schools",
            headers=_auth(login.json()["access_token"]),
            json={
                "name": f"Operations School {suffix}",
                "code": f"OPS-{suffix}",
                "admin_email": admin_email,
                "admin_name": "Operations Admin",
                "admin_password": "test-school-admin-123",
            },
        )
        assert school.status_code == 201

        admin_login = client.post(
            "/api/v1/auth/login",
            json={"email": admin_email, "password": "test-school-admin-123"},
        )
        assert admin_login.status_code == 200
        headers = _auth(admin_login.json()["access_token"])

        year = client.post(
            "/api/v1/academic-years",
            headers=headers,
            json={
                "name": f"2026-27-{suffix}",
                "starts_on": "2026-04-01",
                "ends_on": "2027-03-31",
                "is_current": True,
            },
        ).json()

        staff = client.post(
            "/api/v1/people/staff",
            headers=headers,
            json={
                "employee_no": f"T-{suffix}",
                "full_name": "Neha Rao",
                "designation": "Teacher",
                "is_teacher": True,
                "joined_on": "2026-04-01",
            },
        ).json()
        student = client.post(
            "/api/v1/people/students",
            headers=headers,
            json={
                "admission_no": f"ADM-{suffix}",
                "first_name": "Riya",
                "last_name": "Shah",
                "joined_on": "2026-04-01",
            },
        ).json()
        subject = client.post(
            "/api/v1/academics/subjects",
            headers=headers,
            json={"code": f"MATH-{suffix}", "name": "Mathematics"},
        ).json()

        withdrawn = client.post(
            f"/api/v1/lifecycle/students/{student['id']}/withdraw",
            headers=headers,
            json={"effective_on": "2026-08-01", "reason": "Transfer"},
        )
        assert withdrawn.status_code == 200
        readmitted = client.post(
            f"/api/v1/lifecycle/students/{student['id']}/readmit",
            headers=headers,
            json={"effective_on": "2026-08-15", "reason": "Transfer cancelled"},
        )
        assert readmitted.status_code == 200

        terminated = client.post(
            f"/api/v1/lifecycle/staff/{staff['id']}/terminate",
            headers=headers,
            json={"effective_on": "2026-08-20", "reason": "Contract ended"},
        )
        assert terminated.status_code == 200
        rehired = client.post(
            f"/api/v1/lifecycle/staff/{staff['id']}/rehire",
            headers=headers,
            json={"effective_on": "2026-09-01", "reason": "New contract"},
        )
        assert rehired.status_code == 200

        document = client.post(
            "/api/v1/reports/documents",
            headers=headers,
            json={
                "owner_type": "student",
                "owner_id": student["id"],
                "category": "important_record",
                "title": "Important Student Record",
                "storage_url": f"s3://campus-docs/{suffix}/record.pdf",
                "mime_type": "application/pdf",
                "is_important": True,
            },
        )
        assert document.status_code == 201

        exam = client.post(
            "/api/v1/reports/exams",
            headers=headers,
            json={"academic_year_id": year["id"], "name": f"Mid Term {suffix}"},
        ).json()
        score = client.put(
            f"/api/v1/reports/exams/{exam['id']}/scores",
            headers=headers,
            json={
                "student_id": student["id"],
                "subject_id": subject["id"],
                "marks_obtained": "86",
                "max_marks": "100",
            },
        )
        assert score.status_code == 200
        assert score.json()["grade"] == "A"

        card = client.post(
            f"/api/v1/reports/exams/{exam['id']}/students/{student['id']}/publish",
            headers=headers,
            json={"teacher_remarks": "Good progress"},
        )
        assert card.status_code == 201
        assert float(card.json()["percentage"]) == 86.0

        salary = client.post(
            "/api/v1/finance/salary-structures",
            headers=headers,
            json={
                "staff_id": staff["id"],
                "basic_salary": "50000",
                "allowances": "5000",
                "standard_deductions": "3000",
                "effective_from": "2026-09-01",
            },
        )
        assert salary.status_code == 201
        assert float(salary.json()["net_salary"]) == 52000.0

        payroll = client.post(
            "/api/v1/finance/payroll-runs",
            headers=headers,
            json={"year": 2026, "month": 9},
        ).json()
        generated = client.post(
            f"/api/v1/finance/payroll-runs/{payroll['id']}/generate",
            headers=headers,
        )
        assert generated.status_code == 200
        assert generated.json()["generated"] == 1

        payroll_view = client.get(
            f"/api/v1/finance/payroll-runs/{payroll['id']}", headers=headers
        ).json()
        item_id = payroll_view["items"][0]["id"]
        paid = client.post(
            f"/api/v1/finance/payroll-items/{item_id}/pay",
            headers=headers,
            json={"payment_method": "bank_transfer", "payment_reference": f"PAY-{suffix}"},
        )
        assert paid.status_code == 200

        category = client.post(
            "/api/v1/finance/expense-categories",
            headers=headers,
            json={"name": f"Utilities-{suffix}"},
        ).json()
        expense = client.post(
            "/api/v1/finance/expenses",
            headers=headers,
            json={
                "category_id": category["id"],
                "amount": "7500",
                "incurred_on": "2026-09-10",
                "description": "Electricity bill",
            },
        )
        assert expense.status_code == 201

        summary = client.get("/api/v1/finance/summary", headers=headers)
        assert summary.status_code == 200
        assert float(summary.json()["payroll_paid"]) == 52000.0
        assert float(summary.json()["other_expenditure"]) == 7500.0
