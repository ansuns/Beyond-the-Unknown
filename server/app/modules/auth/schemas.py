from pydantic import BaseModel, ConfigDict, Field


class WeChatLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wx_code: str = Field(min_length=1, max_length=512)
    request_id: str = Field(min_length=1, max_length=128)
