import hashlib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from config.db import supabase


DOC_TABLE = "docs"
CHUNK_TABLE = "chunks"


def _utc_now() -> str:
    return datetime.utcnow().isoformat()


def _as_obj(row: dict | None):
    return SimpleNamespace(**row) if row else None


def compute_file_hash(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_existing_document(user_id: str, content_hash: str):
    response = (
        supabase.table(DOC_TABLE)
        .select("*")
        .eq("user_id", user_id)
        .eq("content_hash", content_hash)
        .eq("status", "ingested")
        .execute()
    )

    for doc in response.data or []:
        chunks = (
            supabase.table(CHUNK_TABLE)
            .select("id")
            .eq("document_id", doc["id"])
            .execute()
        )
        if chunks.data:
            return _as_obj(doc)

        supabase.table(DOC_TABLE).update(
            {"status": "failed", "updated_at": _utc_now()}
        ).eq("id", doc["id"]).execute()

    return None


def get_document_for_reupload(user_id: str, content_hash: str):
    response = (
        supabase.table(DOC_TABLE)
        .select("*")
        .eq("user_id", user_id)
        .eq("content_hash", content_hash)
        .in_("status", ["deleted", "failed", "pending", "processing"])
        .limit(1)
        .execute()
    )
    return _as_obj((response.data or [None])[0])


def create_document(
    user_id: str,
    file_name: str,
    file_path: Path,
    file_url: str,
):
    content_hash = compute_file_hash(file_path)
    existing = get_existing_document(user_id, content_hash)
    if existing:
        return existing.id, content_hash, existing

    reupload = get_document_for_reupload(user_id, content_hash)
    if reupload:
        response = (
            supabase.table(DOC_TABLE)
            .update(
                {
                    "filename": file_name,
                    "url": file_url,
                    "status": "pending",
                    "updated_at": _utc_now(),
                }
            )
            .eq("id", reupload.id)
            .eq("user_id", user_id)
            .execute()
        )
        row = (response.data or [None])[0]
        if not row:
            raise RuntimeError("Supabase did not return the reusable document")
        return row["id"], content_hash, _as_obj(row)

    payload = {
        "user_id": user_id,
        "filename": file_name,
        "url": file_url,
        "content_hash": content_hash,
        "status": "pending",
        "created_at": _utc_now(),
    }
    response = supabase.table(DOC_TABLE).insert(payload).execute()
    row = (response.data or [None])[0]
    if not row:
        raise RuntimeError("Supabase did not return the created document")

    return row["id"], content_hash, _as_obj(row)


def _mark_document(document_id: int, status: str):
    response = (
        supabase.table(DOC_TABLE)
        .update({"status": status, "updated_at": _utc_now()})
        .eq("id", document_id)
        .execute()
    )
    return _as_obj((response.data or [None])[0])


def mark_document_processing(document_id: int):
    return _mark_document(document_id, "processing")


def mark_document_ingested(document_id: int):
    return _mark_document(document_id, "ingested")


def mark_document_failed(document_id: int):
    return _mark_document(document_id, "failed")


def mark_document_deleted(document_id: int):
    return _mark_document(document_id, "deleted")
