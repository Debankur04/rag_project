# Sparse retrieval using Elasticsearch's native BM25 scoring.

from typing import Any

from config.settings import settings

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    from elasticsearch import Elasticsearch

    _client = Elasticsearch(settings.ELASTICSEARCH_URL)
    return _client


def _ensure_index() -> None:
    client = _get_client()
    if client.indices.exists(index=settings.ELASTICSEARCH_INDEX):
        return

    client.indices.create(
        index=settings.ELASTICSEARCH_INDEX,
        mappings={
            "properties": {
                "user_id": {"type": "keyword"},
                "document_id": {"type": "integer"},
                "vector_id": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "source": {"type": "keyword"},
                "text": {"type": "text"},
            }
        },
    )


def _document_id(user_id: str, document_id: int, chunk_index: int) -> str:
    return f"{user_id}:{document_id}:{chunk_index}"


def bulk_index_chunks(chunks: list[dict[str, Any]]) -> None:
    if not chunks:
        return

    try:
        from elasticsearch.helpers import bulk

        _ensure_index()
        actions = []
        for chunk in chunks:
            actions.append(
                {
                    "_op_type": "index",
                    "_index": settings.ELASTICSEARCH_INDEX,
                    "_id": _document_id(
                        str(chunk["user_id"]),
                        int(chunk["document_id"]),
                        int(chunk["chunk_index"]),
                    ),
                    "_source": {
                        "user_id": str(chunk["user_id"]),
                        "document_id": int(chunk["document_id"]),
                        "vector_id": chunk.get("vector_id"),
                        "chunk_index": int(chunk["chunk_index"]),
                        "source": chunk.get("source"),
                        "text": chunk["text"],
                    },
                }
            )

        bulk(_get_client(), actions)
    except Exception as exc:
        print(f"Elasticsearch sparse indexing skipped: {exc}")


def delete_document_chunks(user_id: str, document_id: int) -> None:
    try:
        _get_client().delete_by_query(
            index=settings.ELASTICSEARCH_INDEX,
            query={
                "bool": {
                    "filter": [
                        {"term": {"user_id": str(user_id)}},
                        {"term": {"document_id": int(document_id)}},
                    ]
                }
            },
            conflicts="proceed",
            refresh=True,
        )
    except Exception as exc:
        print(f"Elasticsearch document cleanup skipped: {exc}")


def delete_user_chunks(user_id: str) -> None:
    try:
        _get_client().delete_by_query(
            index=settings.ELASTICSEARCH_INDEX,
            query={"term": {"user_id": str(user_id)}},
            conflicts="proceed",
            refresh=True,
        )
    except Exception as exc:
        print(f"Elasticsearch user cleanup skipped: {exc}")


def bm25_search(user_id: str, query: str, top_k: int) -> list[dict[str, Any]]:
    try:
        response = _get_client().search(
            index=settings.ELASTICSEARCH_INDEX,
            body={
                "size": top_k,
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"user_id": str(user_id)}},
                        ],
                        "must": [
                            {
                                "match": {
                                    "text": {
                                        "query": query,
                                        "operator": "or",
                                    }
                                }
                            }
                        ],
                    }
                },
                "_source": [
                    "user_id",
                    "document_id",
                    "vector_id",
                    "chunk_index",
                    "source",
                    "text",
                ],
            },
        )
    except Exception as exc:
        print(f"Elasticsearch BM25 search skipped: {exc}")
        return []

    results = []
    for rank, hit in enumerate(response["hits"]["hits"], start=1):
        chunk = hit["_source"]
        item = {
            "id": _document_id(
                str(chunk["user_id"]),
                int(chunk["document_id"]),
                int(chunk["chunk_index"]),
            ),
            "key": chunk.get("vector_id")
            or _document_id(
                str(chunk["user_id"]),
                int(chunk["document_id"]),
                int(chunk["chunk_index"]),
            ),
            "vector_id": chunk.get("vector_id"),
            "document_id": chunk.get("document_id"),
            "chunk_index": chunk.get("chunk_index"),
            "source": chunk.get("source"),
            "text": chunk["text"],
            "score": float(hit.get("_score") or 0.0),
            "rank": rank,
            "retriever": "bm25",
        }
        results.append(item)

    return results
