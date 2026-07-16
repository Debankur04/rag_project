from doc_ingestion.dto.Doc_dto import DeleteDocRequest

def delete_doc(payload: DeleteDocRequest, user_id: str):
    from doc_ingestion.services.delete import delete_document

    result = delete_document(
        user_id=user_id,
        doc_id=payload.doc_id
    )

    return {"message": "Document deleted", "result": result}
