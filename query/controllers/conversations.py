from fastapi import HTTPException, status

from query.dto.Conversation_dto import (
    CreateConversationRequest,
    RenameConversationRequest,
)
from query.services.conversations import (
    create_conversation,
    delete_conversation,
    get_conversation_messages,
    list_conversations,
    rename_conversation,
)


def create_conversation_controller(payload: CreateConversationRequest, user_id: str):
    return create_conversation(user_id=user_id, title=payload.title)


def list_conversations_controller(user_id: str):
    return {"conversations": list_conversations(user_id)}


def get_conversation_controller(conversation_id: int, user_id: str):
    try:
        return get_conversation_messages(user_id=user_id, conversation_id=conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def rename_conversation_controller(
    conversation_id: int,
    payload: RenameConversationRequest,
    user_id: str,
):
    try:
        return rename_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
            title=payload.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def delete_conversation_controller(conversation_id: int, user_id: str):
    try:
        return delete_conversation(user_id=user_id, conversation_id=conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
