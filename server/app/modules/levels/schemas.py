from uuid import UUID

from pydantic import BaseModel, Field


class LevelEnterRequest(BaseModel):
    level_id: str = Field(min_length=1, max_length=64)
    entrance_id: str = Field(min_length=1, max_length=64)


class LevelRunRequest(BaseModel):
    run_id: UUID


class LevelPositionRequest(BaseModel):
    model_config = {"allow_inf_nan": False}

    run_id: UUID
    x: float
    y: float
