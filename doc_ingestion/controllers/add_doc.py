from uuid import uuid4
from rag_project.doc_ingestion.dto.Doc_dto import AddDocRequest
from fastapi import HTTPException
from rag_project.doc_ingestion.tasks.ingest_tasks import ingest_document
from rag_project.doc_ingestion.services.add_pdf import ingest_pdf
import tempfile
import httpx
from pathlib import Path
from uuid import uuid4



def add_doc(payload: AddDocRequest,db):
    ingestion_id = str(uuid4())

    try:
        # 1. Create temp path
        temp_dir = Path(tempfile.gettempdir()) / "doc_ingestion"
        temp_dir.mkdir(parents=True, exist_ok=True)

        temp_path = temp_dir / f"{uuid4()}_{payload.file_name}"

        ingest_document.delay(
            payload.tenant_id,
            payload.file_name,
            payload.supabase_url,
            ingestion_id,
        )

        # 2. Download file from Supabase
        with httpx.Client(timeout=60.0) as client:
            response = client.get(payload.supabase_url)
            response.raise_for_status()
            temp_path.write_bytes(response.content)

        # 3. Pass REAL FILE PATH
        ingest_pdf(
            db,
            tenant_id=payload.tenant_id,
            file_path=str(temp_path),  # ✅ THIS is the fix
            url=payload.supabase_url
        )

        return {
            "message": "Document ingestion completed",
            "ingestion_id": ingestion_id,
            "status": "success",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))