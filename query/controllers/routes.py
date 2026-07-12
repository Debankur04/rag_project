from fastapi import APIRouter, Request

from query.dto.Conversation_dto import (
    CreateConversationRequest,
    RenameConversationRequest,
)
from query.dto.Query_dto import NewQueryRequest, NewQueryResponse


router = APIRouter(tags=["query"])


@router.post("/query", response_model=NewQueryResponse)
async def query_endpoint(payload: NewQueryRequest, request: Request):
    from query.controllers.query import query_controller

    return await query_controller(payload, user_id=request.state.app_user["id"])


@router.post("/conversations")
def create_conversation_endpoint(payload: CreateConversationRequest, request: Request):
    from query.controllers.conversations import create_conversation_controller

    return create_conversation_controller(payload, user_id=request.state.app_user["id"])


@router.get("/conversations")
def list_conversations_endpoint(request: Request):
    from query.controllers.conversations import list_conversations_controller

    return list_conversations_controller(user_id=request.state.app_user["id"])


@router.get("/conversations/{conversation_id}")
def get_conversation_endpoint(conversation_id: int, request: Request):
    from query.controllers.conversations import get_conversation_controller

    return get_conversation_controller(
        conversation_id=conversation_id,
        user_id=request.state.app_user["id"],
    )


@router.patch("/conversations/{conversation_id}")
def rename_conversation_endpoint(
    conversation_id: int,
    payload: RenameConversationRequest,
    request: Request,
):
    from query.controllers.conversations import rename_conversation_controller

    return rename_conversation_controller(
        conversation_id=conversation_id,
        payload=payload,
        user_id=request.state.app_user["id"],
    )


@router.delete("/conversations/{conversation_id}")
def delete_conversation_endpoint(conversation_id: int, request: Request):
    from query.controllers.conversations import delete_conversation_controller

    return delete_conversation_controller(
        conversation_id=conversation_id,
        user_id=request.state.app_user["id"],
    )
