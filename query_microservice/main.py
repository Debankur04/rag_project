from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi import FastAPI, Request, HTTPException, Depends
from rag_project.query_microservice.dto.Query_dto import NewQueryResponse, NewQueryRequest
from fastapi.responses import JSONResponse
from starlette.middleware import Middleware

from rag_project.query_microservice.controllers.health import health_check
from rag_project.query_microservice.controllers.query import query_controller
from rag_project.query_microservice.middleware.rate_limiter import RateLimitMiddleware

from rag_project.query_microservice.dto.Query_dto import NewQueryResponse
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from rag_project.query_microservice.models.init_db import init_db
from rag_project.query_microservice.config.db_config import get_db

middleware = [Middleware(RateLimitMiddleware)]

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan, middleware=middleware)

init_db()

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.get("/")
async def root():
    return {"message": "OK"}

@app.get("/health")
async def health(db: Session = Depends(get_db)):
    return health_check(db)

@app.post("/query", response_model=NewQueryResponse)
async def query_endpoint(payload: NewQueryRequest):
    return await query_controller(payload)
