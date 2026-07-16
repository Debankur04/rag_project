# Dense retrieval against the existing per-user Qdrant collections.

from typing import Any

from config.db import qdrant


def _result_key(result: dict[str, Any]) -> str:
    vector_id = result.get("vector_id")
    if vector_id:
        return str(vector_id)
    return f"{result.get('document_id')}:{result.get('chunk_index')}"


def dense_search(
    user_id: str,
    embedding: list[float],
    top_k: int,
) -> list[dict[str, Any]]:
    collection_name = f"user_{user_id}"
    if not qdrant.collection_exists(collection_name=collection_name):
        return []

    search_result = qdrant.query_points(
        collection_name=collection_name,
        prefetch=[],
        query=embedding,
        limit=top_k,
    )

    results = []
    for rank, point in enumerate(search_result.points, start=1):
        payload = point.payload or {}
        text = payload.get("text") or payload.get("content")
        if not text:
            continue

        item = {
            "id": str(point.id),
            "vector_id": str(point.id),
            "document_id": payload.get("document_id"),
            "chunk_index": payload.get("chunk_index"),
            "source": payload.get("source"),
            "text": text,
            "score": float(getattr(point, "score", 0.0) or 0.0),
            "rank": rank,
            "retriever": "dense",
        }
        item["key"] = _result_key(item)
        results.append(item)

    return results
