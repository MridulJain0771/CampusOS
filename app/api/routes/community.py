from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession, require_roles, school_id_for
from app.models.community import Announcement, CommunityComment, CommunityPost, SchoolEvent
from app.models.core import User
from app.models.enums import Role
from app.schemas.community import AnnouncementCreate, CommentCreate, EventCreate, PostCreate
from app.services.audit import audit

router = APIRouter(prefix="/community", tags=["community"])


def audience_visible(user: User, audience: str) -> bool:
    if audience == "all":
        return True
    if audience == "students":
        return user.role == Role.STUDENT.value
    if audience == "parents":
        return user.role == Role.PARENT.value
    if audience == "staff":
        return user.role in {Role.SCHOOL_ADMIN.value, Role.STAFF.value, Role.TEACHER.value, Role.ACCOUNTANT.value}
    return True


@router.post("/posts", status_code=201)
async def create_post(payload: PostCreate, db: DbSession, actor: CurrentUser) -> dict:
    post = CommunityPost(school_id=school_id_for(actor), author_user_id=actor.id, **payload.model_dump())
    db.add(post)
    await db.flush()
    await audit(db, actor, "community.post.create", "community_post", post.id)
    await db.commit()
    return {"id": post.id, **payload.model_dump(), "author_user_id": actor.id, "created_at": post.created_at}


@router.get("/posts")
async def list_posts(db: DbSession, actor: CurrentUser, class_section_id: int | None = None) -> list[dict]:
    school_id = school_id_for(actor)
    query = select(CommunityPost).where(CommunityPost.school_id == school_id)
    if class_section_id is not None:
        query = query.where(or_(CommunityPost.class_section_id.is_(None), CommunityPost.class_section_id == class_section_id))
    rows = (await db.scalars(query.order_by(CommunityPost.is_pinned.desc(), CommunityPost.created_at.desc()).limit(100))).all()
    visible = [row for row in rows if audience_visible(actor, row.audience)]
    return [{"id": p.id, "author_user_id": p.author_user_id, "class_section_id": p.class_section_id, "audience": p.audience, "title": p.title, "body": p.body, "is_pinned": p.is_pinned, "created_at": p.created_at} for p in visible]


@router.post("/posts/{post_id}/comments", status_code=201)
async def comment(post_id: int, payload: CommentCreate, db: DbSession, actor: CurrentUser) -> dict:
    school_id = school_id_for(actor)
    post = await db.scalar(select(CommunityPost).where(CommunityPost.id == post_id, CommunityPost.school_id == school_id))
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    item = CommunityComment(school_id=school_id, post_id=post_id, author_user_id=actor.id, body=payload.body)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "post_id": post_id, "author_user_id": actor.id, "body": item.body, "created_at": item.created_at}


@router.post("/announcements", status_code=201)
async def create_announcement(payload: AnnouncementCreate, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF, Role.TEACHER))) -> dict:
    item = Announcement(school_id=school_id_for(actor), created_by_user_id=actor.id, **payload.model_dump())
    db.add(item)
    await db.flush()
    await audit(db, actor, "announcement.create", "announcement", item.id)
    await db.commit()
    return {"id": item.id, **payload.model_dump(), "created_by_user_id": actor.id, "published_at": item.published_at}


@router.get("/announcements")
async def list_announcements(db: DbSession, actor: CurrentUser) -> list[dict]:
    rows = (await db.scalars(select(Announcement).where(Announcement.school_id == school_id_for(actor)).order_by(Announcement.published_at.desc()).limit(100))).all()
    rows = [a for a in rows if audience_visible(actor, a.audience)]
    return [{"id": a.id, "title": a.title, "body": a.body, "audience": a.audience, "class_section_id": a.class_section_id, "published_at": a.published_at, "expires_at": a.expires_at} for a in rows]


@router.post("/events", status_code=201)
async def create_event(payload: EventCreate, db: DbSession, actor: User = Depends(require_roles(Role.SCHOOL_ADMIN, Role.STAFF, Role.TEACHER))) -> dict:
    if payload.ends_at and payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=400, detail="Event end must be after start")
    event = SchoolEvent(school_id=school_id_for(actor), created_by_user_id=actor.id, **payload.model_dump())
    db.add(event)
    await db.flush()
    await audit(db, actor, "event.create", "school_event", event.id)
    await db.commit()
    return {"id": event.id, **payload.model_dump()}


@router.get("/events")
async def list_events(db: DbSession, actor: CurrentUser) -> list[dict]:
    rows = (await db.scalars(select(SchoolEvent).where(SchoolEvent.school_id == school_id_for(actor)).order_by(SchoolEvent.starts_at).limit(100))).all()
    return [{"id": e.id, "title": e.title, "description": e.description, "class_section_id": e.class_section_id, "starts_at": e.starts_at, "ends_at": e.ends_at} for e in rows]
