from datetime import datetime
from rag_project.doc_ingestion_microservice.config.db import supabase, qdrant

from sqlalchemy import text

def health_check(db):
    status = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "api": "ok",
            "relational_db": "unknown",
            "storage": "unknown",
            "vector_db": "unknown"
        }
    }

    # ---- SQLAlchemy DB check ----
    try:
        db.execute(text("SELECT 1"))
        status["services"]["relational_db"] = "ok"
    except Exception as e:
        status["services"]["relational_db"] = "error"

    # ---- Supabase Storage check ----
    try:
        supabase.storage.list_buckets()
        status["services"]["storage"] = "ok"
    except Exception as e:
        status["services"]["storage"] = "error"

    # ---- Qdrant check ----
    try:
        qdrant.get_collections()
        status["services"]["vector_db"] = "ok"
    except Exception:
        status["services"]["vector_db"] = "error"

    # ---- Overall status ----
    if "error" in status["services"].values():
        status["status"] = "degraded"

    return status