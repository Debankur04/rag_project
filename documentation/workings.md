# System Internals

A technical walkthrough of the Hybrid RAG Backend — covering the document ingestion pipeline, the hybrid query pipeline, and all supporting subsystems. This document is intended for engineers who want to understand how the system works at the implementation level.

---

## Contents

1. [System Overview](#1-system-overview)
2. [Document Ingestion Pipeline](#2-document-ingestion-pipeline)
   - [Text Extraction](#text-extraction)
   - [Chunking](#chunking)
   - [Embedding](#embedding)
   - [Dual Indexing](#dual-indexing)
   - [Rollback on Failure](#rollback-on-failure)
3. [Hybrid Query Pipeline](#3-hybrid-query-pipeline)
   - [Semantic Cache](#31-semantic-cache)
   - [Input Guardrails](#32-input-guardrails)
   - [Embedding](#33-embedding)
   - [BM25 Sparse Retrieval](#34-bm25-sparse-retrieval)
   - [Dense Vector Retrieval](#35-dense-vector-retrieval)
   - [Reciprocal Rank Fusion](#36-reciprocal-rank-fusion)
   - [Cohere Cross-Encoder Reranking](#37-cohere-cross-encoder-reranking)
   - [Prompt Construction](#38-prompt-construction)
   - [LLM Routing and Invocation](#39-llm-routing-and-invocation)
   - [Output Validation](#310-output-validation)
   - [Conversation Persistence](#311-conversation-persistence)
4. [Authentication](#4-authentication)
5. [Middleware Stack](#5-middleware-stack)
6. [Data Layer](#6-data-layer)
7. [Configuration](#7-configuration)

---

## 1. System Overview

The Hybrid RAG Backend is a **multi-user document intelligence service**. Each user can upload PDF documents and query them in natural language. The system responds with answers that are grounded exclusively in the user's uploaded content.

The architecture has three primary modules:

- **`auth`** — authentication flows backed by Supabase Auth
- **`doc_ingestion`** — PDF processing pipeline that populates both a dense vector index and a sparse keyword index
- **`query`** — hybrid retrieval pipeline that combines BM25 and dense search, fuses results with RRF, reranks with Cohere, and calls a cost-routed LLM

**Core design guarantees:**

| Guarantee | Implementation |
|-----------|---------------|
| Grounded answers | System prompt explicitly prohibits prior knowledge; LLM must cite retrieved context |
| User isolation | Per-user Qdrant collections; `user_id` filter on every Elasticsearch query; ownership checks before all mutations |
| Graceful degradation | Elasticsearch failures fall back to dense-only; Cohere failures fall back to top-N RRF results |
| No cross-user cache hits | Cache keys are scoped to `sha256(user_id:query_text)` |

---

## 2. Document Ingestion Pipeline

The full flow from file upload to a searchable, indexed document:

```
POST /add_doc (or /add_docs)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  1. Validate file (.pdf extension check)                 │
│  2. Write to temp path                                   │
│  3. Compute SHA-256 content hash                         │
│  4. Query Supabase docs table for existing hash          │
│        ├─ Match found + chunks exist → return duplicate  │
│        └─ No match → create doc record (status=pending)  │
│  5. Update status to "processing"                        │
│  6. Extract text                                         │
│        ├─ PyPDF (text-native PDFs)                       │
│        └─ Tesseract OCR fallback (image-based PDFs)      │
│  7. Chunk with RecursiveCharacterTextSplitter            │
│     (chunk_size=1000, overlap=200)                       │
│  8. Embed each chunk (all-MiniLM-L6-v2 via fastembed)   │
│  9. Dual-write:                                          │
│        ├─ Upsert to Qdrant → collection user_<id>        │
│        ├─ Bulk index to Elasticsearch → rag_chunks       │
│        └─ Insert rows to Supabase → chunks table         │
│ 10. Update doc status to "ingested"                      │
└─────────────────────────────────────────────────────────┘
        │
        ▼
   Return { id, chunk_count, duplicate, status }
```

### Text Extraction

**Primary path — `PyPDFLoader`:**
For text-native PDFs, LangChain's `PyPDFLoader` extracts text directly from the PDF structure. This is fast and accurate for the majority of documents.

**Fallback path — Tesseract OCR:**
If every extracted page is empty (indicating an image-based or scanned document), the system falls back to:

1. **`pdf2image.convert_from_path()`** — renders each PDF page as a PNG.
2. **OpenCV preprocessing** — converts to grayscale and applies binary thresholding to improve contrast and reduce noise before OCR.
3. **`pytesseract.image_to_string()`** — extracts text from the preprocessed image.

Temporary image files are created with a UUID prefix to prevent collisions and are removed immediately after processing each page.

### Chunking

**Splitter:** `RecursiveCharacterTextSplitter` from LangChain  
**Chunk size:** 1,000 characters  
**Overlap:** 200 characters

The recursive splitter attempts to break text at natural semantic boundaries in this priority order: `\n\n` → `\n` → `.` → ` ` → character-level. This produces chunks that are more likely to contain complete, coherent thoughts — critical for retrieval quality. The 200-character overlap ensures that sentences straddling a chunk boundary appear in both adjacent chunks, preventing boundary-edge retrieval misses.

### Embedding

Each chunk is embedded using **`sentence-transformers/all-MiniLM-L6-v2`** via the **fastembed** library, producing a 384-dimensional float vector. fastembed is a lightweight, pure-Python library that avoids PyTorch and CUDA dependencies, simplifying the Dockerfile significantly.

The embedding function is centralised in `config/embeddings.py` and used identically during ingestion and query time. This is a deliberate constraint — any change to the embedding model must be reflected in both contexts simultaneously, because mixing models in the same Qdrant collection produces meaningless similarity scores.

### Dual Indexing

Each chunk is written to three locations in sequence within the same ingestion call:

| Destination | What is written | Access pattern |
|-------------|----------------|----------------|
| **Qdrant** `user_<id>` | 384-dim vector + payload `{document_id, source, chunk_index, text, user_id}` | Nearest-neighbour semantic search at query time |
| **Elasticsearch** `rag_chunks` | Fields `{user_id, document_id, vector_id, chunk_index, source, text}` | BM25 keyword search, filtered by `user_id` |
| **Supabase** `chunks` | `{document_id, vector_id, chunk_index, content}` | Chunk–document mapping; vector ID lookup for deletion |

The Elasticsearch document ID follows the scheme `user_id:document_id:chunk_index`, making writes idempotent — re-ingesting the same document (after duplicate detection resolves the hash mismatch) overwrites existing entries rather than creating duplicates.

### Rollback on Failure

If an exception is raised after vectors have been written, the pipeline executes a coordinated rollback:

1. Qdrant vectors are deleted by the collected list of `vector_id`s.
2. Elasticsearch chunks are removed via `delete_by_query` on `user_id` + `document_id`.
3. The document record's `status` is set to `"failed"` in Supabase.

This ensures no partial state is left in any store, and the ingestion can be safely retried.

---

## 3. Hybrid Query Pipeline

The full flow from query text to a grounded answer:

```
POST /query { text, conversation_id? }
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ 1. Get or create conversation; insert user message        │
│ 2. Check Redis cache (key = sha256(user_id:query_text))   │
│        ├─ Cache hit → insert assistant message, return    │
│        └─ Cache miss → continue                           │
│ 3. Sanitize input (injection detection + PII masking)     │
│ 4. Embed query (all-MiniLM-L6-v2)                         │
│ 5. BM25 search → top 20 candidates (Elasticsearch)        │
│ 6. Dense search → top 20 candidates (Qdrant) [concurrent] │
│ 7. RRF fusion → single ranked list, up to 20 candidates   │
│ 8. Cohere rerank → top 10 final candidates                │
│ 9. Build grounded prompt with reranked context            │
│10. Intent classify → select LLM tier                      │
│11. Invoke LLM (async, with latency tracking)              │
│12. Validate output (length, repetition, hallucination)    │
│13. Cache result; insert assistant message                 │
└───────────────────────────────────────────────────────────┘
        │
        ▼
   Return { query_id, conversation_id, answer, token_usage }
```

### 3.1 Semantic Cache

Every query first checks Redis for a cached response.

- **Cache key:** `sha256(f"{user_id}:{query_text}")` — scoped by user to prevent cross-contamination between users' distinct document sets
- **Storage:** Redis string, JSON-serialised
- **TTL:** `CACHE_TTL_SECONDS` (default: 600 seconds)

A cache hit bypasses embedding, retrieval, reranking, and the LLM call entirely. The cached answer is inserted into the conversation history and returned. This significantly reduces latency and API costs for repeated queries.

### 3.2 Input Guardrails

All query text passes through a multi-layer sanitisation function before any external service is called.

**Text normalisation** produces a clean version of the input:
- Lowercased
- Whitespace collapsed to single spaces
- Leading and trailing whitespace stripped

This normalised text is used as the embedding input, ensuring consistent vector representations for semantically identical queries with different formatting.

**Prompt injection detection** scans the input for patterns that attempt to override the system prompt:

| Pattern | Severity | Risk Score |
|---------|----------|-----------|
| `ignore (previous/all) instructions` | High | +3 |
| `jailbreak` | High | +3 |
| `DAN mode` | High | +3 |
| `forget your (system/instructions)` | High | +3 |
| `<script>`, `<iframe>`, `<object>` | High | +2 |
| `you are now` | Medium | +1 |
| `pretend (you are/to be)` | Medium | +1 |
| Repeated `you are` / `act as` / `system prompt` (>2 occurrences) | — | +2 |

The cumulative `risk_score` is logged. A configurable block threshold is planned for a future release.

**PII masking** identifies sensitive data before it reaches the LLM API or the cache:

| PII Type | Detection Pattern | Action |
|----------|------------------|--------|
| Credit card | 13–16 digit sequences | Redacted → `[REDACTED_CREDIT_CARD]` |
| SSN | `\d{3}-\d{2}-\d{4}` | Redacted → `[REDACTED_SSN]` |
| Passport | `[A-Z]{1,2}\d{6,9}` | Detected and logged |
| Email address | Standard RFC 5322 regex | Detected and logged |
| Phone number | 10-digit sequences | Detected and logged |

High-risk PII (financial identifiers, government IDs) is redacted from the text before any external call. Lower-risk types are logged but preserved, as they may represent legitimate search context.

### 3.3 Embedding

The sanitised query text is embedded using the same `all-MiniLM-L6-v2` model that was used during ingestion. The embedding call is dispatched via `asyncio.to_thread()` to avoid blocking the event loop while the CPU-bound embedding model runs.

Using the identical model for both ingestion and retrieval is mandatory for correctness — the query vector must occupy the same semantic space as the document chunk vectors.

### 3.4 BM25 Sparse Retrieval

The query is issued to Elasticsearch as a BM25 `match` query, strictly filtered by `user_id`:

```json
{
  "query": {
    "bool": {
      "filter": [{ "term": { "user_id": "<user-uuid>" } }],
      "must": [{
        "match": {
          "text": { "query": "<normalised query>", "operator": "or" }
        }
      }]
    }
  }
}
```

BM25 scores documents based on term frequency and inverse document frequency, rewarding exact token overlap. It excels at surfacing documents that contain specific product codes, clause identifiers, proper nouns, or technical terms that share no semantic proximity with conceptually similar phrases.

**Returns:** Up to `HYBRID_RETRIEVAL_TOP_K` (default: 20) results, each annotated with `rank`, `bm25_score`, and `retriever: "bm25"`.

**Failure mode:** If Elasticsearch is unreachable, the function catches the exception, logs it, and returns an empty list. The pipeline continues with dense-only results.

### 3.5 Dense Vector Retrieval

The query embedding is used to perform approximate nearest-neighbour search against the user's Qdrant collection:

```python
qdrant.query_points(
    collection_name=f"user_{user_id}",
    query=embedding_vector,     # 384-dimensional float list
    limit=HYBRID_RETRIEVAL_TOP_K
)
```

Dense search captures semantic similarity — paraphrases, synonyms, and conceptually related passages that share no lexical overlap with the query. It is the complement to BM25's exact matching.

**Returns:** Up to 20 results ranked by cosine similarity, annotated with `retriever: "dense"`.

**Failure mode:** If the user has no documents, the Qdrant collection does not exist and the function returns an empty list gracefully.

Both BM25 and dense retrieval run concurrently via `asyncio.to_thread`, so total retrieval latency is bounded by the slower of the two rather than their sum.

### 3.6 Reciprocal Rank Fusion

RRF merges the two independently ranked lists into a single unified ranking without requiring score normalisation.

**Algorithm:**

```
rrf_score(chunk) = Σ  1 / (k + rank_i)
                  i ∈ {bm25, dense}
```

where `k = 60` is a smoothing constant that reduces the outsized influence of top-ranked results.

**Deduplication:** A chunk that appears in both lists is identified by its `vector_id` (or `document_id:chunk_index` as a fallback). Its RRF scores from each list are summed. A chunk retrieved by both systems — demonstrating cross-signal agreement — naturally receives a higher combined score than one found by only a single retriever.

**Output:** A single list of up to `HYBRID_RETRIEVAL_TOP_K` chunks, each annotated with `rrf_score`, unified `rank`, and `retrievers: ["bm25", "dense"]` or the applicable subset.

The key advantage of RRF over weighted score interpolation is that BM25 and cosine similarity scores exist on incomparable scales. RRF uses only ordinal rank, making it mathematically principled and requiring no calibration.

### 3.7 Cohere Cross-Encoder Reranking

The fused candidate list is sent to Cohere's cross-encoder reranker:

```python
client.rerank(
    model="rerank-v4.0-fast",
    query=clean_query_text,
    documents=[chunk["text"] for chunk in fused_candidates],
    top_n=HYBRID_RERANK_TOP_K     # default: 10
)
```

Both BM25 and dense retrieval are **bi-encoder** approaches: the query and each document are encoded independently, and similarity is estimated from their vector representations. This is fast but fundamentally limited — the model cannot attend to how the query and document text interact with each other.

A **cross-encoder** reads the query and each candidate document together in a single forward pass, enabling full cross-attention. This produces dramatically more accurate relevance judgements, particularly for questions where the relevance is implicit or requires multi-step reasoning across a passage.

The result is the top 10 most relevant chunks — the final context window that is passed to the LLM.

**Failure mode:** If `COHERE_API_KEY` is not set, or if the API call fails, the function returns the top-N RRF-ranked candidates unchanged. The pipeline continues to function with hybrid-without-reranking quality.

### 3.8 Prompt Construction

The retrieved chunks are assembled into a grounded system prompt that strictly constrains LLM behaviour:

```
SYSTEM RULES:
You are an information retrieval assistant.

You MUST answer strictly and only using the information provided
in the GROUND TRUTH CONTEXT section.

Rules you must follow:
- Do NOT use prior knowledge.
- Do NOT guess or infer.
- Do NOT add details not present in the context.
- If the answer is not explicitly stated, respond exactly with:
  "I don't have that information."

GROUND TRUTH CONTEXT:
<chunk_1_text>

<chunk_2_text>

...

USER QUERY:
<normalised_query>
```

The context section is populated by joining the top-N reranked chunk texts with `\n\n`. If retrieval returns no results (the user has no documents, or no chunks meet the relevance threshold), the `{{context}}` placeholder is left empty — the grounding rules remain active and the LLM is forced to declare a lack of context.

### 3.9 LLM Routing and Invocation

**Intent classification:**

Before model selection, the query is classified as simple or complex using `llama-3.1-8b-instant` via Groq. The classifier is instructed to return strictly `True` (simple query) or `False` (complex query). Simple queries are routed to the `fast` model tier; complex queries go to the `primary` model.

The classification result is persisted to the Supabase `intent` table, creating a dataset for accuracy analysis and routing threshold tuning over time.

**Model registry:**

| Alias | Model | Provider | Tier |
|-------|-------|----------|------|
| `primary` | `openai/gpt-oss-120b` | Groq | Expensive — used for complex queries |
| `fast` | `llama-3.1-8b-instant` | Groq | Cheap — ~200ms, used for simple queries |
| `fallback` | `google/gemma-4-31b-it:free` | OpenRouter | Cheap — cross-provider failover |

**Fallback chain:** `primary → fast → fallback`

**Circuit breaker:**

Each model maintains a `ModelHealth` object tracking error count, total calls, and a rolling deque of the last 100 latency measurements. A model's circuit opens when:

- **Error rate exceeds 5%** across the rolling window, or
- **p99 latency exceeds 3,000ms**

When the circuit is open, the model is skipped in the fallback chain for a 60-second cooldown period, after which it enters a half-open state that allows a single test call. This pattern prevents a degraded provider from dragging down response times for all users while automatically recovering once conditions improve.

**Invocation:**

The selected LangChain client's `ainvoke()` is called asynchronously. Elapsed time is measured and recorded via `record_success()` or `record_failure()` on the health tracker. Token usage is extracted from `usage_metadata` (Gemini-style) or `response_metadata.token_usage` (OpenAI-style), normalised to a consistent `{input_tokens, output_tokens, model}` shape.

### 3.10 Output Validation

Every LLM response passes through three validation checks before being returned:

| Check | Condition | Result |
|-------|-----------|--------|
| **Minimum length** | Fewer than 15 words | `OutputValidationError` — likely truncation |
| **Repetition ratio** | Fewer than 30% unique words | `OutputValidationError` — likely stuck-loop failure mode |
| **Hallucination signals** | Patterns: `\$\d{4+}`, `"guaranteed price"`, `"confirmed booking"`, `"100% success"`, `"definitely"`, `"always"` | Warning logged; response not blocked |

The first two checks raise exceptions that propagate to the route handler. The hallucination signal scan is currently advisory — it flags overconfident claims for monitoring while allowing the response through.

### 3.11 Conversation Persistence

Every query/answer pair is appended to the conversation thread in Supabase:

1. A `conversations` record is fetched (if `conversation_id` was provided) or created (using the first 80 characters of the query as the title).
2. The user's message is inserted into `messages` with `role = "user"`.
3. After the LLM answer is validated, the assistant's reply is inserted with `role = "assistant"`.
4. The conversation's `updated_at` timestamp is bumped to keep the list sort order current.

Cache hits follow the same path — the cached answer is persisted to the conversation so the history is always complete regardless of cache state.

---

## 4. Authentication

**Provider:** Supabase Auth (JWT issuance and verification).

**Enforcement:** `access_token_middleware` runs as an HTTP middleware on every incoming request. For non-public paths:

1. Extracts the Bearer token from the `Authorization` header.
2. Calls `supabase_auth.auth.get_user(token)` to verify the token against Supabase.
3. Populates `request.state.app_user` with the user's UUID and email.
4. Short-circuits with `HTTP 401` if the token is absent, malformed, or invalid.

Route handlers never perform token verification themselves. They consume `request.state.app_user["id"]` directly, which is guaranteed to be present for any request that reached the handler.

This design means authentication is enforced exactly once, at a single point, making it impossible to accidentally ship an unauthenticated endpoint.

---

## 5. Middleware Stack

Three middleware components apply to all requests, in this evaluation order:

| Order | Middleware | Scope | Mechanism |
|-------|-----------|-------|-----------|
| 1 | `RateLimitMiddleware` | `POST /query` only | Redis `INCR` + `EXPIRE`; rejects with `429` when counter exceeds threshold |
| 2 | `access_token_middleware` | All non-public paths | Supabase JWT verification; rejects with `401` on failure |
| 3 | `api_timing_middleware` | All paths (opt-in) | Attaches `request_id`; emits `[timing] stage=api.total` on completion |

**Rate limiting implementation:**

```python
key = f"rate_limit:{client_ip}"
current = await redis.incr(key)
if current == 1:
    await redis.expire(key, RATE_LIMIT_WINDOW_SECONDS)  # TTL set only on first hit
if current > RATE_LIMIT_REQUESTS:
    raise HTTPException(status_code=429)
```

Setting the TTL only when `current == 1` is important — it prevents the window from being extended on every request, which would effectively never expire a frequently-hitting IP.

**Timing middleware:**

Enabled when `APP_ENV ∈ {dev, development, local}` or `ENABLE_TIMING=true`. Produces structured timing output keyed by `request_id`:

```
[timing] request=<uuid> stage=query.embedding elapsed_ms=14.21
[timing] request=<uuid> stage=query.bm25_search elapsed_ms=48.93 top_k=20
[timing] request=<uuid> stage=query.dense_search elapsed_ms=35.67 top_k=20
[timing] request=<uuid> stage=query.rrf.fuse elapsed_ms=0.41 bm25_count=19 dense_count=20
[timing] request=<uuid> stage=query.rerank elapsed_ms=198.44 candidate_count=20 top_k=10
[timing] request=<uuid> stage=query.llm.invoke elapsed_ms=843.72 model=primary
[timing] request=<uuid> stage=api.total elapsed_ms=1170.83
```

All per-stage timers are implemented as no-op context managers when disabled, contributing zero overhead in production.

---

## 6. Data Layer

Four data stores are used, each selected for a specific role:

### Supabase (PostgreSQL)

The primary relational store for all structured metadata.

| Table | Purpose | Notable Columns |
|-------|---------|----------------|
| `docs` | Document metadata and lifecycle status | `user_id`, `content_hash`, `status` (`pending` → `processing` → `ingested` / `failed` / `deleted`) |
| `chunks` | Mapping between SQL documents and vector store entries | `document_id`, `vector_id`, `chunk_index`, `content` |
| `conversations` | Conversation thread records | `user_id`, `title`, `updated_at` |
| `messages` | Individual query/answer turns | `conversation_id`, `role` (`user`/`assistant`), `content` |
| `intent` | Intent classification log | `query`, `intent` |

All data access goes through the Supabase REST client, enabling Row Level Security policies to be applied at the database layer independently of application code.

### Qdrant

Dense vector store for semantic similarity search.

- **Collection naming:** `user_<user_id>` — one collection per user, providing hard storage isolation
- **Vector configuration:** 384 dimensions, cosine distance metric
- **Point payload:** `{document_id, source, chunk_index, text, user_id}`

The `user_id` in the payload is informational context. The collection boundary is the actual isolation mechanism — a query issued to `user_<alice>` structurally cannot return results from `user_<bob>`.

### Elasticsearch

Sparse BM25 index for keyword-based retrieval.

- **Index:** Single shared index `rag_chunks`; user isolation is enforced via `filter: term: user_id` on every query and `delete_by_query` on every deletion
- **Document ID scheme:** `user_id:document_id:chunk_index` (deterministic, supports idempotent re-indexing)
- **Field mappings:** `user_id` and `source` as `keyword`; `text` as `text` (analysed for BM25)
- **Development deployment:** Docker Compose, single-node, security disabled, 512 MB JVM heap

### Redis

In-memory store for cache and rate limiting.

| Use | Key Pattern | TTL |
|-----|-------------|-----|
| Semantic query cache | `query_cache:sha256(user_id:query_text)` | `CACHE_TTL_SECONDS` (default: 600s) |
| IP rate limiting | `rate_limit:<client_ip>` | `RATE_LIMIT_WINDOW_SECONDS` (default: 60s) |

The query path uses `redis.asyncio` for non-blocking I/O. The rate limiter uses the same async client via `get_redis()`, a lazy-initialised singleton.

---

## 7. Configuration

### LLM Model Registry

`query/config/config.yaml` is the single source of truth for all model definitions and routing rules. It is parsed once at startup and passed to `ModelRouter`. Modifying it requires a server restart.

```yaml
models:
  primary:
    provider: groq
    model_name: openai/gpt-oss-120b
    max_tokens: 4096
    cost_per_1k_input: 0.0006
    cost_per_1k_output: 0.0008
    avg_latency_ms: 850
    tier: expensive

  fast:
    provider: groq
    model_name: llama-3.1-8b-instant
    max_tokens: 2048
    cost_per_1k_input: 0.00005
    cost_per_1k_output: 0.00008
    avg_latency_ms: 200
    tier: cheap

  fallback:
    provider: openrouter
    model_name: google/gemma-4-31b-it:free
    max_tokens: 8192
    cost_per_1k_input: 0.00010
    cost_per_1k_output: 0.00040
    avg_latency_ms: 600
    tier: cheap

routing_rules:
  use_intent_classifier: true
  simple_query_model: fast
  default_model: primary
  fallback_chain: [primary, fast, fallback]
  latency_threshold_ms: 3000
  error_threshold_pct: 5
```

### Application Settings

All environment variables are declared and validated in `config/settings.py` using `pydantic-settings`. The settings object is a module-level singleton imported wherever configuration is needed. Accessing an unset required variable raises a `ValidationError` at startup with a clear field-level error message.
