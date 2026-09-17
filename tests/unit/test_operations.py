from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.operations import SalaryStructureCreate
from app.services.reports import grade_for_percentage


def test_grade_boundaries():
    assert grade_for_percentage(Decimal("91")) == "A+"
    assert grade_for_percentage(Decimal("80")) == "A"
    assert grade_for_percentage(Decimal("69.99")) == "B"
    assert grade_for_percentage(Decimal("39.99")) == "F"


def test_salary_structure_rejects_negative_net():
    with pytest.raises(ValidationError):
        SalaryStructureCreate(
            staff_id=1,
            basic_salary=Decimal("10000"),
            allowances=Decimal("500"),
            standard_deductions=Decimal("11000"),
            effective_from="2026-04-01",
        )
