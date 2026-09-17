from enum import StrEnum


class Role(StrEnum):
    SUPER_ADMIN = "super_admin"
    SCHOOL_ADMIN = "school_admin"
    ACCOUNTANT = "accountant"
    TEACHER = "teacher"
    STAFF = "staff"
    STUDENT = "student"
    PARENT = "parent"


class AttendanceStatus(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"


class InvoiceStatus(StrEnum):
    OPEN = "open"
    PARTIAL = "partial"
    PAID = "paid"
    VOID = "void"


class PaymentStatus(StrEnum):
    SUCCESS = "success"
    REFUNDED = "refunded"
