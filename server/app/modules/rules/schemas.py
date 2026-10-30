from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RulePoint(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    x: float
    y: float


class RuleCastRequest(BaseModel):
    run_id: UUID
    rule_id: str = Field(min_length=1, max_length=64)
    target_id: str | None = Field(default=None, min_length=1, max_length=100)
    target_point: RulePoint | None = None


class RuleRunRequest(BaseModel):
    run_id: UUID


class RuleMaintainRequest(BaseModel):
    run_id: UUID
    target_id: str = Field(min_length=1, max_length=100)
