from typing import List

from fastapi import APIRouter, File, Request, UploadFile

from doc_ingestion.controllers.add_doc import add_doc, add_docs
from doc_ingestion.controllers.delete_doc import delete_doc
from doc_ingestion.controllers.delete_user_data import delete_user_data_controller
from doc_ingestion.dto.Doc_dto import DeleteDocRequest


router = APIRouter(tags=["doc_ingestion"])


@router.post("/add_doc")
async def add_doc_endpoint(
    request: Request,
    file: UploadFile = File(...),
):
    """Upload and ingest a single PDF document.
    
    - **file**: PDF file to upload (required, single file)
    
    Returns the ingestion result with document metadata.
    """
    return add_doc(user_id=request.state.app_user["id"], file=file)


@router.post("/add_docs")
async def add_docs_endpoint(
    request: Request,
    files: List[UploadFile] = File(...),
):
    """Upload and ingest multiple PDF documents in a single request.
    
    - **files**: PDF files to upload (required, multiple files)
    - **Maximum**: 10 files per request
    
    Returns bulk ingestion results with success/failure statistics.
    Each file is processed independently.
    Failed files do not prevent other files from processing.
    """
    return add_docs(user_id=request.state.app_user["id"], files=files)


@router.delete("/delete_doc")
def delete_doc_endpoint(payload: DeleteDocRequest, request: Request):
    return delete_doc(payload, user_id=request.state.app_user["id"])


@router.delete("/delete_user_data")
def delete_user_data_endpoint(request: Request):
    return delete_user_data_controller(user_id=request.state.app_user["id"])
