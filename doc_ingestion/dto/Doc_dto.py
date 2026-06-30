from pydantic import BaseModel

class AddDocRequest(BaseModel):
    tenant_id: int
    file_name: str
    supabase_url: str


class DeleteDocRequest(BaseModel):
    name: str
    doc_id: str
    tenant_id: str