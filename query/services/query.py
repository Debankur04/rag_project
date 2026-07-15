# Change the query pipeline to accomodate for the hybrid model. take the query and give both query and id to both bm25.py and dense.py take both the results and send the return to the rrf.py which result to reranker.py and then use the final return which will be the context back to the existing rag pipeline as context.

import asyncio
import time

from config.settings import settings
from config.timing import async_timed_stage, timed_stage

from query.llmops.config_loader import load_config
from query.llmops.model_router import ModelRouter
from query.llmops.guardrails import sanitize_input, validate_llm_output
from query.rag.bm25 import bm25_search
from query.rag.dense import dense_search
from query.rag.reranker import rerank_chunks
from query.rag.rrf import reciprocal_rank_fusion

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


async def _invoke_llm_with_router(
    user_query: str,
    system_prompt: str,
    user_tier: str = "standard",
    db=None,
    request_id: str | None = None,
):
    # Dynamically select the best model using the router
    with timed_stage("query.llm.select_model", request_id=request_id):
        model_key = router.select_model(user_query, user_tier=user_tier, db=db)
        client = router.get_client(model_key)
    
    start_time = time.time()
    try:
        async with async_timed_stage(
            "query.llm.invoke",
            request_id=request_id,
            model=model_key,
        ):
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
    top_k: int = 5,
    request_id: str | None = None,
):
    # Guardrails: Sanitize both the user query and prompt to extract clean text
    with timed_stage("query.guardrails.input", request_id=request_id):
        sanitized_query_data = sanitize_input(user_query)
        clean_user_query = sanitized_query_data["clean_text"]
        sanitized_prompt_data = sanitize_input(prompt)
        clean_prompt = sanitized_prompt_data["clean_text"]

    async with async_timed_stage("query.embedding", request_id=request_id):
        embedding = await asyncio.to_thread(
            lambda: _get_embeddings().embed_query(clean_user_query)
        )

    retrieval_top_k = max(top_k, settings.HYBRID_RETRIEVAL_TOP_K)
    async with async_timed_stage(
        "query.bm25_search",
        request_id=request_id,
        top_k=retrieval_top_k,
    ):
        sparse_results = await asyncio.to_thread(
            bm25_search,
            user_id,
            clean_user_query,
            retrieval_top_k,
        )

    async with async_timed_stage(
        "query.dense_search",
        request_id=request_id,
        top_k=retrieval_top_k,
    ):
        dense_results = await asyncio.to_thread(
            dense_search,
            user_id,
            embedding,
            retrieval_top_k,
        )

    with timed_stage(
        "query.rrf.fuse",
        request_id=request_id,
        bm25_count=len(sparse_results),
        dense_count=len(dense_results),
    ):
        fused_results = reciprocal_rank_fusion(
            [sparse_results, dense_results],
            k=60,
            limit=retrieval_top_k,
        )

    async with async_timed_stage(
        "query.rerank",
        request_id=request_id,
        candidate_count=len(fused_results),
        top_k=settings.HYBRID_RERANK_TOP_K,
    ):
        results = await asyncio.to_thread(
            rerank_chunks,
            clean_user_query,
            fused_results,
            settings.HYBRID_RERANK_TOP_K,
        )

    if not results:
        raw_output, token_usage = await _invoke_llm_with_router(
            clean_user_query,
            clean_prompt,
            db=db,
            request_id=request_id,
        )
        
        # Guardrails: Output validation
        with timed_stage("query.guardrails.output", request_id=request_id):
            validated_output = validate_llm_output(raw_output)
        
        return {
            "answer": validated_output,
            "token_usage": token_usage
        }

    with timed_stage(
        "query.context.build",
        request_id=request_id,
        result_count=len(results),
    ):
        context = "\n\n".join(
            result["text"]
            for result in results
            if result.get("text")
        )

    final_prompt = clean_prompt.replace("{{context}}", context)

    raw_output, token_usage = await _invoke_llm_with_router(
        clean_user_query,
        final_prompt,
        db=db,
        request_id=request_id,
    )
    
    # Guardrails: Output validation
    with timed_stage("query.guardrails.output", request_id=request_id):
        validated_output = validate_llm_output(raw_output)
    
    return {
        "answer": validated_output,
        "token_usage": token_usage
    }
