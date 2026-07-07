from pydantic import BaseModel


class DeleteDocRequest(BaseModel):
    name: str
    doc_id: str
    tenant_id: str
