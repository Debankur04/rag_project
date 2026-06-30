from fastapi import FastAPI, Request, HTTPException, Depends

from controllers.health import health_check
from controllers.add_doc import add_doc
from controllers.delete_doc import delete_doc
from controllers.delete_tenant import delete_tenant_controller

from dto.Doc_dto import AddDocRequest, DeleteDocRequest
from dto.Tenant_dto import DeleteTenant

from sqlalchemy.orm import Session

from models.init_db import init_db
from config.db_config import get_db

from dto.Query_dto import NewQueryResponse, NewQueryRequest
from fastapi.responses import JSONResponse
from starlette.middleware import Middleware

from controllers.health import health_check
from controllers.query import query_controller
from middleware.rate_limiter import RateLimitMiddleware

from dto.Query_dto import NewQueryResponse
from sqlalchemy.orm import Session
from models.init_db import init_db
from config.db_config import get_db

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background workers (easy to scale by changing the number here)
    # start_workers(num_workers=3)
    yield


app = FastAPI(lifespan=lifespan)
# app.add_middleware(APIKeyMiddleware)
init_db()

@app.get("/")
async def root():
    return {"message": "OK"}

@app.get("/health")
async def health(db: Session = Depends(get_db)):
    return health_check(db)


@app.post("/add_doc")
async def add_doc_endpoint(payload: AddDocRequest,db: Session = Depends(get_db)):
    return add_doc(payload,db)


@app.delete("/delete_doc")
async def delete_doc_endpoint(
    payload: DeleteDocRequest,
    db: Session = Depends(get_db)
):
    return delete_doc(payload=payload, db=db)


@app.delete("/delete_tenant")
async def delete_tenant_endpoint(
    payload: DeleteTenant,
    db: Session = Depends(get_db)
):
    return delete_tenant_controller(payload, db)