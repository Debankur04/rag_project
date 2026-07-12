import tempfile
from pathlib import Path
from shutil import copyfileobj
from uuid import uuid4

from fastapi import HTTPException, UploadFile


def add_doc(user_id: int, file: UploadFile):
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

        from doc_ingestion.services.add_pdf import ingest_pdf

        result = ingest_pdf(
            user_id=user_id,
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


def add_docs(user_id: int, files: list[UploadFile]):
    results = []
    for file in files:
        try:
            results.append(add_doc(user_id=user_id, file=file))
        except HTTPException as exc:
            results.append(
                {
                    "file_name": file.filename,
                    "status": "failed",
                    "error": exc.detail,
                }
            )

    success_count = sum(1 for result in results if result.get("status") == "success")
    return {
        "message": "Bulk document ingestion completed",
        "total": len(results),
        "success": success_count,
        "failed": len(results) - success_count,
        "results": results,
    }
