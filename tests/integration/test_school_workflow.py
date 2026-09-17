import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.integration
def test_school_class_and_fee_workflow():
    suffix = uuid.uuid4().hex[:8]
    with TestClient(app) as client:
        super_login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@campusos.io", "password": "integration-admin-password"},
        )
        assert super_login.status_code == 200
        super_headers = {"Authorization": f"Bearer {super_login.json()['access_token']}"}

        school = client.post(
            "/api/v1/schools",
            headers=super_headers,
            json={
                "name": f"Campus School {suffix}",
                "code": f"CS-{suffix}",
                "admin_email": f"school-{suffix}@example.com",
                "admin_name": "School Admin",
                "admin_password": "school-admin-password",
            },
        )
        assert school.status_code == 201

        admin_login = client.post(
            "/api/v1/auth/login",
            json={"email": f"school-{suffix}@example.com", "password": "school-admin-password"},
        )
        assert admin_login.status_code == 200
        headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        year = client.post(
            "/api/v1/academic-years",
            headers=headers,
            json={"name": "2026-27", "starts_on": "2026-04-01", "ends_on": "2027-03-31", "is_current": True},
        )
        assert year.status_code == 201
        year_id = year.json()["id"]

        teacher = client.post(
            "/api/v1/people/staff",
            headers=headers,
            json={"employee_no": f"T-{suffix}", "full_name": "Anita Sharma", "department": "Science", "designation": "Teacher", "is_teacher": True},
        )
        assert teacher.status_code == 201
        teacher_id = teacher.json()["id"]

        student = client.post(
            "/api/v1/people/students",
            headers=headers,
            json={"admission_no": f"ADM-{suffix}", "first_name": "Aarav", "last_name": "Jain"},
        )
        assert student.status_code == 201
        student_id = student.json()["id"]

        room = client.post(
            "/api/v1/academics/classrooms",
            headers=headers,
            json={"name": f"Room-{suffix}", "building": "Main Block", "floor": "2", "capacity": 40},
        )
        assert room.status_code == 201
        room_id = room.json()["id"]

        section = client.post(
            "/api/v1/academics/sections",
            headers=headers,
            json={
                "academic_year_id": year_id,
                "grade_name": "Grade 8",
                "section_name": "A",
                "classroom_id": room_id,
                "class_teacher_staff_id": teacher_id,
            },
        )
        assert section.status_code == 201
        section_id = section.json()["id"]

        subject = client.post(
            "/api/v1/academics/subjects",
            headers=headers,
            json={"code": f"SCI-{suffix}", "name": "Science"},
        )
        assert subject.status_code == 201
        subject_id = subject.json()["id"]

        assigned = client.post(
            f"/api/v1/academics/sections/{section_id}/subjects",
            headers=headers,
            json={"subject_id": subject_id, "teacher_staff_id": teacher_id},
        )
        assert assigned.status_code == 201

        enrolled = client.post(
            f"/api/v1/academics/sections/{section_id}/enrollments",
            headers=headers,
            json={"student_id": student_id, "academic_year_id": year_id, "roll_no": "12"},
        )
        assert enrolled.status_code == 201

        class_view = client.get(f"/api/v1/academics/students/{student_id}/class", headers=headers)
        assert class_view.status_code == 200
        assert class_view.json()["class"]["grade"] == "Grade 8"
        assert class_view.json()["classroom"]["id"] == room_id
        assert class_view.json()["subjects"][0]["teacher_staff_id"] == teacher_id

        invoice = client.post(
            "/api/v1/fees/invoices",
            headers=headers,
            json={
                "academic_year_id": year_id,
                "student_id": student_id,
                "due_date": "2026-06-10",
                "discount_amount": "3000.00",
                "late_fee_amount": "500.00",
                "lines": [
                    {"description": "Tuition Fee", "amount": "30000.00"},
                    {"description": "Transport Fee", "amount": "8000.00"},
                    {"description": "Annual Fee", "amount": "5000.00"},
                ],
            },
        )
        assert invoice.status_code == 201
        invoice_id = invoice.json()["id"]
        assert Decimal(str(invoice.json()["total_amount"])) == Decimal("40500.00")

        payment_headers = {**headers, "Idempotency-Key": f"pay-{suffix}"}
        payment = client.post(
            f"/api/v1/fees/invoices/{invoice_id}/payments",
            headers=payment_headers,
            json={"amount": "20000.00", "method": "upi", "reference": f"UPI-{suffix}"},
        )
        assert payment.status_code == 201

        replay = client.post(
            f"/api/v1/fees/invoices/{invoice_id}/payments",
            headers=payment_headers,
            json={"amount": "20000.00", "method": "upi", "reference": f"UPI-{suffix}"},
        )
        assert replay.status_code == 200
        assert replay.headers["X-Idempotent-Replay"] == "true"

        ledger = client.get(f"/api/v1/fees/students/{student_id}/ledger", headers=headers)
        assert ledger.status_code == 200
        assert Decimal(str(ledger.json()["outstanding"])) == Decimal("20500.00")
