from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.middleware import Middleware

from auth.controllers.auth import router as auth_router
from config.db_config import get_db
from doc_ingestion.controllers.health import health_check
from doc_ingestion.controllers.routes import router as doc_ingestion_router
from doc_ingestion.models.init_db import init_db as init_doc_ingestion_db
from query.controllers.routes import router as query_router
from query.middleware.rate_limiter import RateLimitMiddleware
from query.models.init_db import init_db as init_query_db


middleware = [Middleware(RateLimitMiddleware)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_doc_ingestion_db()
    init_query_db()
    yield


app = FastAPI(
    title="RAG Backend API",
    version="1.0.0",
    lifespan=lifespan,
    middleware=middleware,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/")
async def root():
    return {"message": "RAG Backend Running"}


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    return health_check(db)


app.include_router(query_router)
app.include_router(doc_ingestion_router)
app.include_router(auth_router)
