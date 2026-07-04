from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from rag_project.config.db_config import get_db
from rag_project.doc_ingestion.controllers.add_doc import add_doc
from rag_project.doc_ingestion.controllers.delete_doc import delete_doc
from rag_project.doc_ingestion.controllers.delete_tenant import delete_tenant_controller
from rag_project.doc_ingestion.dto.Doc_dto import AddDocRequest, DeleteDocRequest
from rag_project.doc_ingestion.dto.Tenant_dto import DeleteTenant


router = APIRouter(tags=["doc_ingestion"])


@router.post("/add_doc")
def add_doc_endpoint(payload: AddDocRequest, db: Session = Depends(get_db)):
    return add_doc(payload, db)


@router.delete("/delete_doc")
def delete_doc_endpoint(payload: DeleteDocRequest, db: Session = Depends(get_db)):
    return delete_doc(payload, db)


@router.delete("/delete_tenant")
def delete_tenant_endpoint(payload: DeleteTenant, db: Session = Depends(get_db)):
    return delete_tenant_controller(payload, db)
