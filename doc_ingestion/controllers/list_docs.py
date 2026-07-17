from doc_ingestion.services.documents_chunks import list_documents_for_user


def list_docs(user_id: str):
    return {"documents": list_documents_for_user(user_id)}
