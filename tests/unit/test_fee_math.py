from decimal import Decimal

from app.services.fees import invoice_total, payment_status


def test_invoice_total_applies_discount_and_late_fee():
    assert invoice_total(Decimal("30000"), Decimal("3000"), Decimal("500")) == Decimal("27500")


def test_payment_status_transitions():
    total = Decimal("40500")
    assert payment_status(total, Decimal("0")) == "open"
    assert payment_status(total, Decimal("20000")) == "partial"
    assert payment_status(total, Decimal("40500")) == "paid"
