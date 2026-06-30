from typing import Optional
from pydantic import BaseModel


class NewQueryRequest(BaseModel):
    text: str
    tenant_id: int


class NewQueryResponse(BaseModel):
    query_id: str
    answer: str
    token_usage: Optional[dict] = None