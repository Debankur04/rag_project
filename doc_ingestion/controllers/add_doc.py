import tempfile
from pathlib import Path
from shutil import copyfileobj
from uuid import uuid4

from fastapi import HTTPException, UploadFile


def add_doc(user_id: str, file: UploadFile):
    """Process a single PDF file upload."""
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
            "file_name": file_name,
            "ingestion_id": ingestion_id,
            "status": "success",
            "document": result,
            "error": None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def add_docs(user_id: str, files: list[UploadFile]):
    """Process multiple PDF file uploads.
    
    Args:
        user_id: The user ID from the request context
        files: List of files to process
        
    Returns:
        A dictionary with bulk upload results and statistics
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided. At least one file is required.")
    
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files per request. Please upload in batches.")
    
    results = []
    for file in files:
        try:
            result = add_doc(user_id=user_id, file=file)
            results.append(result)
        except HTTPException as exc:
            results.append(
                {
                    "file_name": file.filename or "unknown",
                    "status": "failed",
                    "error": exc.detail,
                    "ingestion_id": None,
                    "document": None,
                }
            )
        except Exception as e:
            results.append(
                {
                    "file_name": file.filename or "unknown",
                    "status": "failed",
                    "error": f"Unexpected error: {str(e)}",
                    "ingestion_id": None,
                    "document": None,
                }
            )

    success_count = sum(1 for result in results if result.get("status") == "success")
    failed_count = len(results) - success_count
    
    return {
        "message": "Bulk document ingestion completed",
        "total": len(results),
        "success": success_count,
        "failed": failed_count,
        "results": results,
    }
