from pydantic import BaseModel

class DeleteTenant(BaseModel):
    tenant_id:int
