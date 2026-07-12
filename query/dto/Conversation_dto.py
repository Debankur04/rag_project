from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class RenameConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
