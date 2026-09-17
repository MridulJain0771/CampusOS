from datetime import date

from pydantic import BaseModel, Field


class SchoolCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=2, max_length=40)
    timezone: str = "Asia/Kolkata"
    currency: str = "INR"
    admin_email: str
    admin_name: str
    admin_password: str = Field(min_length=8)


class SchoolResponse(BaseModel):
    id: int
    name: str
    code: str
    timezone: str
    currency: str
    is_active: bool

    model_config = {"from_attributes": True}


class AcademicYearCreate(BaseModel):
    name: str
    starts_on: date
    ends_on: date
    is_current: bool = False
