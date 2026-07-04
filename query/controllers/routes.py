from fastapi import APIRouter

from rag_project.query.controllers.query import query_controller
from rag_project.query.dto.Query_dto import NewQueryRequest, NewQueryResponse


router = APIRouter(tags=["query"])


@router.post("/query", response_model=NewQueryResponse)
async def query_endpoint(payload: NewQueryRequest):
    return await query_controller(payload)
