from datetime import datetime

from config.db import supabase


CONVERSATION_TABLE = "conversations"
MESSAGE_TABLE = "messages"


def _utc_now() -> str:
    return datetime.utcnow().isoformat()


def get_or_create_conversation(
    user_id: int,
    conversation_id: int | None,
    first_message: str,
) -> dict:
    if conversation_id is not None:
        response = (
            supabase.table(CONVERSATION_TABLE)
            .select("*")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]
        raise ValueError("Conversation not found for current user")

    title = first_message.strip()[:80] or "New conversation"
    response = (
        supabase.table(CONVERSATION_TABLE)
        .insert(
            {
                "user_id": user_id,
                "title": title,
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
            }
        )
        .execute()
    )
    if not response.data:
        raise RuntimeError("Unable to create conversation")
    return response.data[0]


def create_conversation(user_id: int, title: str | None = None) -> dict:
    response = (
        supabase.table(CONVERSATION_TABLE)
        .insert(
            {
                "user_id": user_id,
                "title": (title or "New conversation").strip()[:255],
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
            }
        )
        .execute()
    )
    if not response.data:
        raise RuntimeError("Unable to create conversation")
    return response.data[0]


def list_conversations(user_id: int) -> list[dict]:
    response = (
        supabase.table(CONVERSATION_TABLE)
        .select("*")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return response.data or []


def get_conversation(user_id: int, conversation_id: int) -> dict:
    response = (
        supabase.table(CONVERSATION_TABLE)
        .select("*")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise ValueError("Conversation not found for current user")
    return response.data[0]


def get_conversation_messages(user_id: int, conversation_id: int) -> dict:
    conversation = get_conversation(user_id, conversation_id)
    messages = (
        supabase.table(MESSAGE_TABLE)
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .execute()
    )
    return {"conversation": conversation, "messages": messages.data or []}


def rename_conversation(user_id: int, conversation_id: int, title: str) -> dict:
    get_conversation(user_id, conversation_id)
    response = (
        supabase.table(CONVERSATION_TABLE)
        .update({"title": title.strip(), "updated_at": _utc_now()})
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        raise RuntimeError("Unable to rename conversation")
    return response.data[0]


def delete_conversation(user_id: int, conversation_id: int) -> dict:
    get_conversation(user_id, conversation_id)
    supabase.table(MESSAGE_TABLE).delete().eq("conversation_id", conversation_id).execute()
    supabase.table(CONVERSATION_TABLE).delete().eq("id", conversation_id).eq("user_id", user_id).execute()
    return {"conversation_id": conversation_id, "status": "deleted"}


def add_message(conversation_id: int, role: str, content: str) -> dict:
    response = (
        supabase.table(MESSAGE_TABLE)
        .insert(
            {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "created_at": _utc_now(),
            }
        )
        .execute()
    )
    if not response.data:
        raise RuntimeError("Unable to create message")

    supabase.table(CONVERSATION_TABLE).update(
        {"updated_at": _utc_now()}
    ).eq("id", conversation_id).execute()

    return response.data[0]
