
from rag_project.query_service.models.intent import Intent


def insert_intent(db,query: str, intent_res: str):
    new_intent = Intent(
        query = query,
        intent = intent_res
    )

    db.add(new_intent)
    db.commit()
    db.refresh(new_intent)

    return new_intent