import asyncio
import time

from config.db import qdrant

from query.llmops.config_loader import load_config
from query.llmops.model_router import ModelRouter
from query.llmops.guardrails import sanitize_input, validate_llm_output

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

embeddings = None

# Load configuration and initialize ModelRouter
config = load_config()
router = ModelRouter(config)


def _get_embeddings():
    global embeddings
    if embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings

        embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL_NAME)
    return embeddings

async def _invoke_llm_with_router(user_query: str, system_prompt: str, user_tier: str = "standard", db=None):
    # Dynamically select the best model using the router
    model_key = router.select_model(user_query, user_tier=user_tier, db=db)
    client = router.get_client(model_key)
    
    start_time = time.time()
    try:
        res = await client.ainvoke(system_prompt)
        latency_ms = (time.time() - start_time) * 1000
        router.record_success(model_key, latency_ms)
        
        # Extract token usage directly from response
        input_tokens = 0
        output_tokens = 0
        if hasattr(res, "usage_metadata") and res.usage_metadata:
            input_tokens = res.usage_metadata.get("input_tokens", 0)
            output_tokens = res.usage_metadata.get("output_tokens", 0)
        elif hasattr(res, "response_metadata") and res.response_metadata:
            token_usage = res.response_metadata.get("token_usage", {})
            if token_usage:
                input_tokens = token_usage.get("prompt_tokens", 0)
                output_tokens = token_usage.get("completion_tokens", 0)

        model_name = config["models"][model_key]["model_name"]
                
        return res.content, {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model": model_name
        }
    except Exception as e:
        router.record_failure(model_key, e)
        raise e


async def run_query(
    user_id: int,
    user_query: str,
    prompt: str,
    db=None,
    top_k: int = 5
):
    # Guardrails: Sanitize both the user query and prompt to extract clean text
    sanitized_query_data = sanitize_input(user_query)
    clean_user_query = sanitized_query_data["clean_text"]
    
    sanitized_prompt_data = sanitize_input(prompt)
    clean_prompt = sanitized_prompt_data["clean_text"]

    embedding = await asyncio.to_thread(lambda: _get_embeddings().embed_query(clean_user_query))

    search_result = await asyncio.to_thread(
        qdrant.query_points,
        collection_name=f"user_{user_id}",
        prefetch=[],
        query=embedding,
        limit=top_k
    )

    results = search_result.points

    if not results:
        raw_output, token_usage = await _invoke_llm_with_router(clean_user_query, clean_prompt, db=db)
        
        # Guardrails: Output validation
        validated_output = validate_llm_output(raw_output)
        
        return {
            "answer": validated_output,
            "token_usage": token_usage
        }

    context = "\n\n".join(
        r.payload["text"]
        for r in results
        if r.payload and "text" in r.payload
    )

    final_prompt = clean_prompt.replace("{{context}}", context)

    raw_output, token_usage = await _invoke_llm_with_router(clean_user_query, final_prompt, db=db)
    
    # Guardrails: Output validation
    validated_output = validate_llm_output(raw_output)
    
    return {
        "answer": validated_output,
        "token_usage": token_usage
    }
