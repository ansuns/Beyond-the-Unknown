from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import engine
from app.realtime.manager import map_connections

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.app_env != "test":
        await map_connections.start(
            settings.redis_url,
            settings.map_presence_ttl_seconds,
        )
    try:
        yield
    finally:
        await map_connections.close()
        await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)

# The WeChat client talks through wx.request and needs no CORS. The Cocos web
# preview is a normal browser page on another port, so without this the whole
# client fails at the first fetch. Local only: a deployed API must name its
# real origins rather than inheriting a wildcard from a dev convenience.
if settings.local_login_allowed():
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d+$",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id")
    if not request_id or len(request_id) > 128:
        request_id = str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


app.include_router(api_router, prefix="/api/v1")


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    if not await map_connections.ping():
        raise RuntimeError("Redis is not ready")
    return {"status": "ready"}
