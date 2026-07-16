from typing import Any


EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_embedding_model: Any = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from fastembed import TextEmbedding

        _embedding_model = TextEmbedding(model_name=EMBED_MODEL_NAME)
    return _embedding_model


def embed_query(text: str) -> list[float]:
    vector = next(_get_embedding_model().embed([text]))
    if hasattr(vector, "tolist"):
        return vector.tolist()
    return list(vector)
