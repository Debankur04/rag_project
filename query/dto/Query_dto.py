from typing import Optional
from pydantic import BaseModel


class NewQueryRequest(BaseModel):
    text: str
    conversation_id: Optional[int] = None


class NewQueryResponse(BaseModel):
    query_id: str
    conversation_id: Optional[int] = None
    answer: str
    token_usage: Optional[dict] = None
