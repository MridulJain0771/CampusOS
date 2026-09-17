from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis

from app.api.routes import academics, attendance, auth, community, dashboard, fees, health, notifications, people, schools
from app.core.config import settings
from app.db.session import engine
from app.services.bootstrap import bootstrap_superadmin


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await bootstrap_superadmin()
    yield
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Multi-tenant school management platform for academics, fees, people, community and operations.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(schools.router, prefix="/api/v1")
app.include_router(people.router, prefix="/api/v1")
app.include_router(academics.router, prefix="/api/v1")
app.include_router(fees.router, prefix="/api/v1")
app.include_router(attendance.router, prefix="/api/v1")
app.include_router(community.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.mount("/admin-ui", StaticFiles(directory="frontend", html=True), name="admin-ui")


@app.get("/")
async def root() -> dict:
    return {
        "name": "CampusOS API",
        "docs": "/docs",
        "health": "/health/live",
        "modules": ["schools", "users", "students", "staff", "classes", "fees", "attendance", "community", "notifications"],
    }
