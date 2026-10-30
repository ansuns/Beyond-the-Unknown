from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.players.router import router as players_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(players_router, prefix="/player", tags=["player"])
