from datetime import datetime
from rag_project.query_microservice.config.db import supabase, qdrant
from rag_project.query_microservice.llmops.config_loader import load_config
from sqlalchemy import text
from rag_project.query_microservice.services.redis_client import get_redis
from rag_project.query_microservice.services.mongo_logger import mongo_client

def health_check(db):
    status = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "api": "ok",
            "relational_db": "unknown",
            "storage": "unknown",
            "vector_db": "unknown",
            "redis": "unknown",
            "mongo": "unknown"
        }
    }

    # ---- SQLAlchemy DB check ----
    try:
        db.execute(text("SELECT 1"))
        status["services"]["relational_db"] = "ok"
    except Exception:
        status["services"]["relational_db"] = "error"

    # ---- Supabase Storage check ----
    try:
        supabase.storage.list_buckets()
        status["services"]["storage"] = "ok"
    except Exception:
        status["services"]["storage"] = "error"

    # ---- Qdrant check ----
    try:
        qdrant.get_collections()
        status["services"]["vector_db"] = "ok"
    except Exception:
        status["services"]["vector_db"] = "error"

    # ---- Redis check ----
    try:
        redis = get_redis()
        redis.ping()
        status["services"]["redis"] = "ok"
    except Exception:
        status["services"]["redis"] = "error"

    # ---- MongoDB check ----
    try:
        mongo_client.admin.command("ping")
        status["services"]["mongo"] = "ok"
    except Exception:
        status["services"]["mongo"] = "error"

    # ---- Overall status ----
    if "error" in status["services"].values():
        status["status"] = "degraded"

    # ---- LLM Configuration Data ----
    try:
        config = load_config()
        status["llm_models"] = config.get("models", {})
        status["routing_rules"] = config.get("routing_rules", {})
    except Exception as e:
        status["llm_models"] = f"Error loading LLM config: {str(e)}"

    return status