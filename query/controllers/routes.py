from fastapi import APIRouter

from query.dto.Query_dto import NewQueryRequest, NewQueryResponse


router = APIRouter(tags=["query"])


@router.post("/query", response_model=NewQueryResponse)
async def query_endpoint(payload: NewQueryRequest):
    from query.controllers.query import query_controller

    return await query_controller(payload)
