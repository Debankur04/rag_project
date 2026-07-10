from fastapi import APIRouter, File, Form, UploadFile

from doc_ingestion.controllers.add_doc import add_doc
from doc_ingestion.controllers.delete_doc import delete_doc
from doc_ingestion.controllers.delete_tenant import delete_tenant_controller
from doc_ingestion.dto.Doc_dto import DeleteDocRequest
from doc_ingestion.dto.Tenant_dto import DeleteTenant


router = APIRouter(tags=["doc_ingestion"])


@router.post("/add_doc")
def add_doc_endpoint(
    tenant_id: int = Form(...),
    file: UploadFile = File(...),
):
    return add_doc(tenant_id=tenant_id, file=file)


@router.delete("/delete_doc")
def delete_doc_endpoint(payload: DeleteDocRequest):
    return delete_doc(payload)


@router.delete("/delete_tenant")
def delete_tenant_endpoint(payload: DeleteTenant):
    return delete_tenant_controller(payload)
