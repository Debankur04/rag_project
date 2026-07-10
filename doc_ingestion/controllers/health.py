from datetime import datetime

from config.db import qdrant, supabase


def health_check():
    status = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "api": "ok",
            "supabase": "unknown",
            "storage": "unknown",
            "vector_db": "unknown",
        },
    }

    try:
        supabase.table("docs").select("id").limit(1).execute()
        status["services"]["supabase"] = "ok"
    except Exception as e:
        print(e)
        status["services"]["supabase"] = "error"

    try:
        supabase.storage.list_buckets()
        status["services"]["storage"] = "ok"
    except Exception:
        status["services"]["storage"] = "error"

    try:
        qdrant.get_collections()
        status["services"]["vector_db"] = "ok"
    except Exception:
        status["services"]["vector_db"] = "error"

    if "error" in status["services"].values():
        status["status"] = "degraded"

    return status
