from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SettleLevelRequest(BaseModel):
    run_id: UUID


class ClaimRewardRequest(BaseModel):
    player_reward_id: UUID


class LeaderboardQuery(BaseModel):
    board_type: Literal["EXPLORE", "CLEAR", "COLLECT"] = "EXPLORE"
    season_type: Literal["WEEKLY", "MONTHLY"] = "WEEKLY"
    limit: int = Field(default=50, ge=1, le=100)
