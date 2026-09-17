from datetime import datetime

from pydantic import BaseModel


class PostCreate(BaseModel):
    class_section_id: int | None = None
    audience: str = "all"
    title: str
    body: str
    is_pinned: bool = False


class CommentCreate(BaseModel):
    body: str


class AnnouncementCreate(BaseModel):
    class_section_id: int | None = None
    audience: str = "all"
    title: str
    body: str
    expires_at: datetime | None = None


class EventCreate(BaseModel):
    class_section_id: int | None = None
    title: str
    description: str | None = None
    starts_at: datetime
    ends_at: datetime | None = None
