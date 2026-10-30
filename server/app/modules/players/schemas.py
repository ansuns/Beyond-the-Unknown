from pydantic import BaseModel, ConfigDict, Field


class SelectCharacterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    character_id: str = Field(min_length=1, max_length=64)
