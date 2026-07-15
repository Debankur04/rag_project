# Sparse retrieval using locally indexed Elasticsearch chunks plus bm25s ranking.

from typing import Any

from config.settings import settings


def _get_client():
    from elasticsearch import Elasticsearch

    return Elasticsearch(settings.ELASTICSEARCH_URL)


def _ensure_index() -> None:
    client = _get_client()
    if client.indices.exists(index=settings.ELASTICSEARCH_INDEX):
        return

    client.indices.create(
        index=settings.ELASTICSEARCH_INDEX,
        mappings={
            "properties": {
                "user_id": {"type": "integer"},
                "document_id": {"type": "integer"},
                "vector_id": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "source": {"type": "keyword"},
                "text": {"type": "text"},
            }
        },
    )


def _document_id(user_id: int, document_id: int, chunk_index: int) -> str:
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
                        int(chunk["user_id"]),
                        int(chunk["document_id"]),
                        int(chunk["chunk_index"]),
                    ),
                    "_source": {
                        "user_id": int(chunk["user_id"]),
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


def delete_document_chunks(user_id: int, document_id: int) -> None:
    try:
        _get_client().delete_by_query(
            index=settings.ELASTICSEARCH_INDEX,
            query={
                "bool": {
                    "filter": [
                        {"term": {"user_id": int(user_id)}},
                        {"term": {"document_id": int(document_id)}},
                    ]
                }
            },
            conflicts="proceed",
            refresh=True,
        )
    except Exception as exc:
        print(f"Elasticsearch document cleanup skipped: {exc}")


def delete_user_chunks(user_id: int) -> None:
    try:
        _get_client().delete_by_query(
            index=settings.ELASTICSEARCH_INDEX,
            query={"term": {"user_id": int(user_id)}},
            conflicts="proceed",
            refresh=True,
        )
    except Exception as exc:
        print(f"Elasticsearch user cleanup skipped: {exc}")


def _load_user_chunks(user_id: int) -> list[dict[str, Any]]:
    response = _get_client().search(
        index=settings.ELASTICSEARCH_INDEX,
        body={
            "size": settings.BM25_CANDIDATE_LIMIT,
            "query": {"term": {"user_id": int(user_id)}},
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
    return [hit["_source"] for hit in response["hits"]["hits"]]


def bm25_search(user_id: int, query: str, top_k: int) -> list[dict[str, Any]]:
    try:
        import bm25s

        chunks = _load_user_chunks(user_id)
        if not chunks:
            return []

        corpus = [chunk["text"] for chunk in chunks]
        corpus_tokens = bm25s.tokenize(corpus)
        retriever = bm25s.BM25()
        retriever.index(corpus_tokens)

        query_tokens = bm25s.tokenize([query])
        indexes, scores = retriever.retrieve(query_tokens, k=min(top_k, len(chunks)))
    except Exception as exc:
        print(f"BM25 sparse search skipped: {exc}")
        return []

    results = []
    for rank, (index, score) in enumerate(zip(indexes[0], scores[0]), start=1):
        chunk = chunks[int(index)]
        item = {
            "id": _document_id(
                int(chunk["user_id"]),
                int(chunk["document_id"]),
                int(chunk["chunk_index"]),
            ),
            "key": chunk.get("vector_id")
            or _document_id(
                int(chunk["user_id"]),
                int(chunk["document_id"]),
                int(chunk["chunk_index"]),
            ),
            "vector_id": chunk.get("vector_id"),
            "document_id": chunk.get("document_id"),
            "chunk_index": chunk.get("chunk_index"),
            "source": chunk.get("source"),
            "text": chunk["text"],
            "score": float(score),
            "rank": rank,
            "retriever": "bm25",
        }
        results.append(item)

    return results
