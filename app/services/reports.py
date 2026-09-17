from decimal import Decimal


def grade_for_percentage(value: Decimal) -> str:
    if value >= 90:
        return "A+"
    if value >= 80:
        return "A"
    if value >= 70:
        return "B+"
    if value >= 60:
        return "B"
    if value >= 50:
        return "C"
    if value >= 40:
        return "D"
    return "F"
