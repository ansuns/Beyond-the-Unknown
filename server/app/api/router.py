from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.maps.router import router as maps_router
from app.modules.levels.router import router as levels_router
from app.modules.players.router import router as players_router
from app.realtime.router import router as realtime_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(players_router, prefix="/player", tags=["player"])
api_router.include_router(maps_router, prefix="/map", tags=["map"])
api_router.include_router(levels_router, prefix="/level", tags=["level"])
api_router.include_router(realtime_router, tags=["realtime"])
