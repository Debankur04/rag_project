from doc_ingestion.dto.Doc_dto import DeleteDocRequest
from doc_ingestion.services.delete import delete_document

def delete_doc(payload: DeleteDocRequest):
    result = delete_document(
        tenant_id=payload.tenant_id,
        doc_id=payload.doc_id
    )

    return {"message": "Document deleted", "result": result}
