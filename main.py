from contextlib import asynccontextmanager
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.middleware import Middleware

from auth.controllers.auth import router as auth_router
from auth.middleware import PUBLIC_PATHS, access_token_middleware
from config.timing import print_timing, timing_enabled
from doc_ingestion.controllers.health import health_check
from doc_ingestion.controllers.routes import router as doc_ingestion_router
from query.controllers.routes import router as query_router
from query.middleware.rate_limiter import RateLimitMiddleware
from fastapi.middleware.cors import CORSMiddleware

middleware = [Middleware(RateLimitMiddleware)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="RAG Backend API",
    version="1.0.0",
    lifespan=lifespan,
    middleware=middleware,
)


app.middleware("http")(access_token_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://poneglyph-sigma.vercel.app",
        "https://poneglyph.debankurdutta.me",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def api_timing_middleware(request: Request, call_next):
    if not timing_enabled():
        return await call_next(request)

    request_id = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["x-request-id"] = request_id
        return response
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        print_timing(
            "api.total",
            elapsed_ms,
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=status_code,
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/")
async def root():
    return {"message": "RAG Backend Running"}


@app.get("/health")
async def health():
    return health_check()


app.include_router(query_router)
app.include_router(doc_ingestion_router)
app.include_router(auth_router)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})[
        "BearerAuth"
    ] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Paste your Supabase access token here. Do not include the word Bearer.",
    }

    for path, methods in openapi_schema.get("paths", {}).items():
        if path in PUBLIC_PATHS:
            continue
        for operation in methods.values():
            if isinstance(operation, dict):
                operation.setdefault("security", [{"BearerAuth": []}])

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
