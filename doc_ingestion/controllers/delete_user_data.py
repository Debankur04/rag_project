from doc_ingestion.services.delete import delete_user_documents


def delete_user_data_controller(user_id: str):
    result = delete_user_documents(user_id)
    return {"message": "User documents deleted", "result": result}
