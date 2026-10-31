from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class LevelSettleRequest(BaseModel):
    run_id: UUID


class RewardClaimRequest(BaseModel):
    player_reward_id: UUID


class SeasonReviewRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    note: str | None = None


class LeaderboardRecomputeRequest(BaseModel):
    board_type: Literal["EXPLORE", "CLEAR", "COLLECT"]
    apply: bool = False
