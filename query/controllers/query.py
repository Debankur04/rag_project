from uuid import uuid4

from rag_project.query.dto.Query_dto import NewQueryRequest, NewQueryResponse
from rag_project.query.services.cache import query_cache
from rag_project.query.services.query import run_query
from rag_project.query.services.prompt import prompt_builder
from rag_project.query.services.mongo_logger import log_query_async


async def query_controller(payload: NewQueryRequest) -> NewQueryResponse:
    query_id = str(uuid4())

    cached_response = await query_cache.get(payload.text)
    if cached_response:
        await log_query_async(
            query_id=query_id,
            query_text=payload.text,
            response=cached_response,
            intent=None,
            status="cached",
        )
        return NewQueryResponse(
            query_id=query_id,
            answer=cached_response["answer"],
            token_usage=cached_response.get("token_usage"),
        )

    prompt = prompt_builder(query=payload.text)
    result = await run_query(
        tenant_id=str(payload.tenant_id),
        user_query=payload.text,
        prompt=prompt,
    )

    await query_cache.set(payload.text, result)
    await log_query_async(
        query_id=query_id,
        query_text=payload.text,
        response=result,
        intent=None,
        status="success",
    )

    return NewQueryResponse(
        query_id=query_id,
        answer=result["answer"],
        token_usage=result.get("token_usage"),
    )