from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from starlette.middleware import Middleware
from sqlalchemy.orm import Session

# -----------------------------
# Database
# -----------------------------
from doc_ingestion.config.db_config import get_db
from doc_ingestion.models.init_db import init_db

# -----------------------------
# Middleware
# -----------------------------
from query_service.middleware.rate_limiter import RateLimitMiddleware

# -----------------------------
# Controllers
# -----------------------------
from doc_ingestion.controllers.health import health_check

# Document Controllers
from doc_ingestion.controllers.add_doc import add_doc
from doc_ingestion.controllers.delete_doc import delete_doc
from doc_ingestion.controllers.delete_tenant import delete_tenant_controller

# Query Controller
from query_service.controllers.query import query_controller

# Auth Controllers
from controllers.auth import (
    login,
    register,
    logout,
    refresh_token,
    verify_token,
    forgot_password,
    reset_password,
)

# -----------------------------
# DTOs
# -----------------------------

# Query DTOs
from query_service.dto.Query_dto import (
    NewQueryRequest,
    NewQueryResponse,
)

# Document DTOs
from doc_ingestion.dto.Doc_dto import (
    AddDocRequest,
    DeleteDocRequest,
)

# Tenant DTO
from doc_ingestion.dto.Tenant_dto import DeleteTenant

# Auth DTOs
from dto.Auth_dto import (
    LoginRequest,
    RegisterRequest,
    RefreshTokenRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)

# -----------------------------
# Lifespan
# -----------------------------
middleware = [
    Middleware(RateLimitMiddleware)
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background workers if required
    # start_workers(num_workers=3)

    init_db()

    yield

    # Cleanup if needed


app = FastAPI(
    title="RAG Backend API",
    version="1.0.0",
    lifespan=lifespan,
    middleware=middleware,
)


# -------------------------------------------------
# Exception Handler
# -------------------------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# =================================================
# Root APIs
# =================================================

@app.get("/")
async def root():
    return {
        "message": "RAG Backend Running"
    }


@app.get("/health")
async def health(db: Session =Depends(get_db)):
    return health_check(db)


# =================================================
# Query APIs
# =================================================

@app.post(
    "/query",
    response_model=NewQueryResponse,
)
async def query_endpoint(
    payload: NewQueryRequest,
):
    return await query_controller(payload)


# =================================================
# Document APIs
# =================================================

@app.post("/add_doc")
async def add_doc_endpoint(
    payload: AddDocRequest,
    db: Session = Depends(get_db),
):
    return add_doc(payload, db)


@app.delete("/delete_doc")
async def delete_doc_endpoint(
    payload: DeleteDocRequest,
    db: Session = Depends(get_db),
):
    return delete_doc(payload, db)


@app.delete("/delete_tenant")
async def delete_tenant_endpoint(
    payload: DeleteTenant,
    db: Session = Depends(get_db),
):
    return delete_tenant_controller(payload, db)


# =================================================
# Authentication APIs
# =================================================

@app.post("/auth/register")
async def register_user(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):
    return register(payload, db)


@app.post("/auth/login")
async def login_user(
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    return login(payload, db)


@app.post("/auth/logout")
async def logout_user(
    request: Request,
    db: Session = Depends(get_db),
):
    return logout(request, db)


@app.post("/auth/refresh")
async def refresh_access_token(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    return refresh_token(payload, db)


@app.get("/auth/verify")
async def verify_access_token(
    request: Request,
    db: Session = Depends(get_db),
):
    return verify_token(request, db)


@app.post("/auth/forgot-password")
async def forgot_password_endpoint(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    return forgot_password(payload, db)


@app.post("/auth/reset-password")
async def reset_password_endpoint(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    return reset_password(payload, db)