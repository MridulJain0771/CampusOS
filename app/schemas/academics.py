from datetime import date, time

from pydantic import BaseModel, Field


class ClassroomCreate(BaseModel):
    name: str
    building: str | None = None
    floor: str | None = None
    capacity: int | None = Field(default=None, ge=1)


class SectionCreate(BaseModel):
    academic_year_id: int
    grade_name: str
    section_name: str
    classroom_id: int | None = None
    class_teacher_staff_id: int | None = None


class SubjectCreate(BaseModel):
    code: str
    name: str


class SubjectTeacherAssign(BaseModel):
    subject_id: int
    teacher_staff_id: int


class EnrollmentCreate(BaseModel):
    student_id: int
    academic_year_id: int
    roll_no: str | None = None


class TimetableCreate(BaseModel):
    class_section_id: int
    subject_id: int
    teacher_staff_id: int
    classroom_id: int | None = None
    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time


class AttendanceMark(BaseModel):
    academic_year_id: int | None = None
    class_section_id: int | None = None
    student_id: int | None = None
    staff_id: int | None = None
    attendance_date: date
    status: str
    notes: str | None = None
