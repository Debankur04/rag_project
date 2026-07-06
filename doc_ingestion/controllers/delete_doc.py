from doc_ingestion.dto.Doc_dto import DeleteDocRequest
from doc_ingestion.services.delete import delete_document

def delete_doc(payload: DeleteDocRequest, db):
    delete_document(
        db=db,
        tenant_id=payload.tenant_id,
        doc_id=payload.doc_id
    )

    return {"message": "Document deleted"}
