from uuid import uuid4

from config.timing import async_timed_stage, timed_stage
from query.dto.Query_dto import NewQueryRequest, NewQueryResponse
from query.services.cache import query_cache
from query.services.conversations import add_message, get_or_create_conversation
from query.services.query import run_query
from query.services.prompt import prompt_builder


async def query_controller(
    payload: NewQueryRequest,
    user_id: str,
    request_id: str | None = None,
) -> NewQueryResponse:
    query_id = str(uuid4())

    with timed_stage("query.conversation.get_or_create", request_id=request_id):
        conversation = get_or_create_conversation(
            user_id=user_id,
            conversation_id=payload.conversation_id,
            first_message=payload.text,
        )
    conversation_id = conversation["id"]

    with timed_stage("query.message.user.insert", request_id=request_id):
        add_message(conversation_id=conversation_id, role="user", content=payload.text)

    cache_key = f"{user_id}:{payload.text}"
    async with async_timed_stage("query.cache.get", request_id=request_id):
        cached_response = await query_cache.get(cache_key)
    if cached_response:
        with timed_stage("query.message.assistant.insert", request_id=request_id):
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

    with timed_stage("query.prompt.build", request_id=request_id):
        prompt = prompt_builder(query=payload.text)

    async with async_timed_stage("query.rag.run", request_id=request_id):
        result = await run_query(
            user_id=user_id,
            user_query=payload.text,
            prompt=prompt,
            request_id=request_id,
        )

    async with async_timed_stage("query.cache.set", request_id=request_id):
        await query_cache.set(cache_key, result)

    with timed_stage("query.message.assistant.insert", request_id=request_id):
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
