from uuid import UUID

from pydantic import BaseModel, Field


class LevelEnterRequest(BaseModel):
    level_id: str = Field(min_length=1, max_length=64)
    entrance_id: str = Field(min_length=1, max_length=64)


class LevelRunRequest(BaseModel):
    run_id: UUID


class LawActionRequest(BaseModel):
    run_id: UUID
    rule_id: str = Field(min_length=1, max_length=64)
    mechanism_id: str = Field(min_length=1, max_length=100)
    action: str = Field(pattern="^(APPLY|RELEASE)$")
