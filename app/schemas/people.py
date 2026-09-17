from datetime import date

from pydantic import BaseModel, EmailStr


class StudentCreate(BaseModel):
    admission_no: str
    first_name: str
    last_name: str = ""
    date_of_birth: date | None = None
    gender: str | None = None
    joined_on: date | None = None
    user_id: int | None = None


class StaffCreate(BaseModel):
    employee_no: str
    full_name: str
    department: str | None = None
    designation: str | None = None
    is_teacher: bool = False
    joined_on: date | None = None
    user_id: int | None = None


class ParentCreate(BaseModel):
    full_name: str
    phone: str | None = None
    email: EmailStr | None = None
    user_id: int | None = None


class LinkParentRequest(BaseModel):
    relation: str = "guardian"
    is_primary: bool = False


class IdCardCreate(BaseModel):
    expires_on: date | None = None
