# Reciprocal Rank Fusion (RRF). Combine BM25 and dense retrieval into one ranked list.

from typing import Any


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]],
    k: int = 60,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    fused: dict[str, dict[str, Any]] = {}

    for results in ranked_lists:
        for rank, result in enumerate(results, start=1):
            key = str(
                result.get("key")
                or result.get("vector_id")
                or f"{result.get('document_id')}:{result.get('chunk_index')}"
            )
            if key not in fused:
                fused[key] = {
                    **result,
                    "key": key,
                    "retrievers": set(),
                    "rrf_score": 0.0,
                }

            fused[key]["rrf_score"] += 1.0 / (k + rank)
            fused[key]["retrievers"].add(result.get("retriever", "unknown"))

    ranked = sorted(
        fused.values(),
        key=lambda item: item["rrf_score"],
        reverse=True,
    )

    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
        item["retrievers"] = sorted(item["retrievers"])

    return ranked[:limit] if limit else ranked
