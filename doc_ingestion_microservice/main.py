
from fastapi import FastAPI, Depends

from rag_project.doc_ingestion_microservice.controllers.health import health_check
from rag_project.doc_ingestion_microservice.controllers.add_doc import add_doc
from rag_project.doc_ingestion_microservice.controllers.delete_doc import delete_doc
from rag_project.doc_ingestion_microservice.controllers.delete_tenant import delete_tenant_controller

from rag_project.doc_ingestion_microservice.dto.Doc_dto import AddDocRequest, DeleteDocRequest
from rag_project.doc_ingestion_microservice.dto.Tenant_dto import DeleteTenant

from sqlalchemy.orm import Session
from contextlib import asynccontextmanager

from rag_project.doc_ingestion_microservice.models.init_db import init_db
from rag_project.doc_ingestion_microservice.config.db_config import get_db

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