from config.db import supabase


def insert_intent(query: str, intent_res: str):
    response = (
        supabase.table("intent")
        .insert({"query": query, "intent": str(intent_res)})
        .execute()
    )
    return (response.data or [None])[0]
