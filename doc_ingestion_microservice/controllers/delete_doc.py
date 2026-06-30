from rag_project.doc_ingestion_microservice.dto.Doc_dto import DeleteDocRequest
from rag_project.doc_ingestion_microservice.services.delete import delete_document

def delete_doc(payload: DeleteDocRequest, db):
    delete_document(
        db=db,
        tenant_id=payload.tenant_id,
        doc_id=payload.doc_id
    )

    return {"message": "Document deleted"}
