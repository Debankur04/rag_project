from uuid import uuid4

from query.dto.Query_dto import NewQueryRequest, NewQueryResponse
from query.services.cache import query_cache
from query.services.conversations import add_message, get_or_create_conversation
from query.services.query import run_query
from query.services.prompt import prompt_builder


async def query_controller(payload: NewQueryRequest, user_id: int) -> NewQueryResponse:
    query_id = str(uuid4())
    conversation = get_or_create_conversation(
        user_id=user_id,
        conversation_id=payload.conversation_id,
        first_message=payload.text,
    )
    conversation_id = conversation["id"]
    add_message(conversation_id=conversation_id, role="user", content=payload.text)

    cached_response = await query_cache.get(f"{user_id}:{payload.text}")
    if cached_response:
        add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=cached_response["answer"],
        )
        return NewQueryResponse(
            query_id=query_id,
            conversation_id=conversation_id,
            answer=cached_response["answer"],
            token_usage=cached_response.get("token_usage"),
        )

    prompt = prompt_builder(query=payload.text)
    result = await run_query(
        user_id=user_id,
        user_query=payload.text,
        prompt=prompt,
    )

    await query_cache.set(f"{user_id}:{payload.text}", result)
    add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=result["answer"],
    )

    return NewQueryResponse(
        query_id=query_id,
        conversation_id=conversation_id,
        answer=result["answer"],
        token_usage=result.get("token_usage"),
    )
