# Cohere reranking for fused hybrid retrieval results.

from typing import Any

from config.settings import settings


def rerank_chunks(
    query: str,
    chunks: list[dict[str, Any]],
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    top_n = top_n or settings.HYBRID_RERANK_TOP_K
    if not chunks:
        return []

    if not settings.COHERE_API_KEY:
        return chunks[:top_n]

    documents = [chunk["text"] for chunk in chunks if chunk.get("text")]
    if not documents:
        return []

    try:
        import cohere

        client = cohere.Client(settings.COHERE_API_KEY)
        response = client.rerank(
            model="rerank-v4.0-fast",
            query=query,
            documents=documents,
            top_n=min(top_n, len(documents)),
        )
    except Exception as exc:
        print(f"Cohere rerank skipped: {exc}")
        return chunks[:top_n]

    reranked = []
    for rank, result in enumerate(response.results, start=1):
        chunk = dict(chunks[result.index])
        chunk["rank"] = rank
        chunk["rerank_score"] = float(result.relevance_score)
        reranked.append(chunk)

    return reranked
