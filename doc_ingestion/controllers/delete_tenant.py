from rag_project.doc_ingestion.dto.Tenant_dto import DeleteTenant
from rag_project.doc_ingestion.services.delete import delete_tenant

def delete_tenant_controller(payload: DeleteTenant, db):
    delete_tenant(db, payload.tenant_id)
    return {"message": "Tenant deleted"}