from pydantic import BaseModel


class DeleteDocRequest(BaseModel):
    doc_id: str
