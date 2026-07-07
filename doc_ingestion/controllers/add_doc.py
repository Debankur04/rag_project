import tempfile
from pathlib import Path
from shutil import copyfileobj
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from doc_ingestion.services.add_pdf import ingest_pdf


def add_doc(tenant_id: int, file: UploadFile, db):
    ingestion_id = str(uuid4())
    temp_path: Path | None = None

    try:
        file_name = Path(file.filename or "document.pdf").name
        if not file_name.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF uploads are supported")

        temp_dir = Path(tempfile.gettempdir()) / "doc_ingestion"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{uuid4()}_{file_name}"

        with temp_path.open("wb") as buffer:
            copyfileobj(file.file, buffer)

        result = ingest_pdf(
            db,
            tenant_id=str(tenant_id),
            file_path=str(temp_path),
            source=file_name,
        )

        return {
            "message": "Document ingestion completed",
            "ingestion_id": ingestion_id,
            "status": "success",
            "document": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
