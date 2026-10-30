from uuid import UUID

from pydantic import BaseModel


class LevelSettleRequest(BaseModel):
    run_id: UUID


class RewardClaimRequest(BaseModel):
    player_reward_id: UUID
