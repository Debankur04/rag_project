# Architecture Decision Records

This document records the key engineering decisions made in the Hybrid RAG Backend. Each entry follows a structured format: the context that motivated the decision, the choice made, the reasoning behind it, and the trade-offs accepted. It is intended to demonstrate the thinking behind the system's design.

---

## Contents

1. [Hybrid Retrieval: BM25 + Dense + RRF](#1-hybrid-retrieval-bm25--dense--rrf)
2. [Cohere Cross-Encoder Reranking](#2-cohere-cross-encoder-reranking)
3. [Elasticsearch for Sparse Retrieval](#3-elasticsearch-for-sparse-retrieval)
4. [Qdrant for Dense Retrieval](#4-qdrant-for-dense-retrieval)
5. [Embedding Model: all-MiniLM-L6-v2 via fastembed](#5-embedding-model-all-minilm-l6-v2-via-fastembed)
6. [Per-User Storage Isolation](#6-per-user-storage-isolation)
7. [Chunking Strategy](#7-chunking-strategy)
8. [PDF Extraction with OCR Fallback](#8-pdf-extraction-with-ocr-fallback)
9. [Dual Indexing on Ingestion](#9-dual-indexing-on-ingestion)
10. [Cost-Aware LLM Routing with Circuit Breaker](#10-cost-aware-llm-routing-with-circuit-breaker)
11. [LLM-Based Intent Classification](#11-llm-based-intent-classification)
12. [OpenRouter as Fallback Provider](#12-openrouter-as-fallback-provider)
13. [Supabase for Auth and Relational Data](#13-supabase-for-auth-and-relational-data)
14. [Conversation Threading](#14-conversation-threading)
15. [Global JWT Middleware](#15-global-jwt-middleware)
16. [User-Scoped Semantic Cache](#16-user-scoped-semantic-cache)
17. [Lazy Client Initialisation](#17-lazy-client-initialisation)
18. [Bulk Document Upload](#18-bulk-document-upload)
19. [Opt-In Timing Instrumentation](#19-opt-in-timing-instrumentation)
20. [Grounded Prompt Design](#20-grounded-prompt-design)
21. [Input Guardrails and PII Masking](#21-input-guardrails-and-pii-masking)
22. [Planned Improvements](#22-planned-improvements)

---

## 1. Hybrid Retrieval: BM25 + Dense + RRF

**Context**

The initial version of this system used dense vector search exclusively. Dense retrieval captures semantic similarity well but has a known weakness: it tends to underperform on queries that contain specific, exact tokens — product identifiers, clause references, proper nouns, numeric codes — because these tokens often do not have a strong signal in the embedding space. A user querying for "ISO 27001 clause 6.1.2" may get semantically related results about risk management but miss the exact clause they asked about.

**Decision**

Run **BM25 sparse retrieval** (Elasticsearch) and **dense semantic retrieval** (Qdrant) in parallel on every query. Merge both result sets using **Reciprocal Rank Fusion (RRF)**.

**Reasoning**

The two retrieval methods are fundamentally complementary:

- Dense search finds passages that are *semantically* related to the query, even when the exact words differ. It handles paraphrases, synonyms, and cross-lingual overlap.
- BM25 finds passages that contain the *exact tokens* present in the query. It is robust to rare terms, proper nouns, and identifiers that lack meaningful vector representations.

Combining them consistently outperforms either approach in isolation on mixed-domain retrieval benchmarks. Documents that surface in *both* result sets receive a naturally boosted score through RRF, rewarding cross-signal agreement.

**Why RRF over weighted score interpolation**

BM25 and cosine similarity scores exist on fundamentally different scales and distributions — a BM25 score of 3.2 and a cosine similarity of 0.87 cannot be meaningfully combined arithmetically without careful, dataset-specific calibration. RRF sidesteps this entirely by using only ordinal rank. With `k=60`, it is parameter-free and has been shown to perform competitively with tuned score combinations across a wide range of retrieval tasks.

**Trade-offs**

- Introduces Elasticsearch as a hard infrastructure dependency. Mitigated by graceful degradation: `bm25_search()` returns an empty list on connection failure, and the pipeline continues with dense-only results.
- Increases ingestion complexity — each document must now be written to two indexes instead of one.

---

## 2. Cohere Cross-Encoder Reranking

**Context**

RRF produces a high-recall merged list of up to 20 candidate chunks. However, both BM25 and dense retrieval are **bi-encoder** approaches: the query and document are encoded independently, and their similarity is estimated from the inner product of two separate vectors. This architecture is computationally efficient but inherently limited — the model cannot observe *how* the query and the document text interact with each other.

The final context window passed to the LLM needs to be high-precision, not just high-recall. Irrelevant chunks in the context degrade answer quality and waste tokens.

**Decision**

After RRF fusion, pass the candidate list through **Cohere `rerank-v4.0-fast`** (a cross-encoder model) to select the top `HYBRID_RERANK_TOP_K` (default: 10) final results.

**Reasoning**

A cross-encoder processes the query and each candidate document as a concatenated input in a single forward pass. The model's full attention mechanism operates across both texts simultaneously, capturing relevance signals that bi-encoder similarity scores cannot — implicit relationships, multi-step reasoning requirements, and passages where relevance depends on context spread across several sentences.

Cohere's hosted API makes this capability available without GPU infrastructure. The `rerank-v4.0-fast` model specifically targets the latency constraints of a retrieval pipeline.

**Graceful degradation**

If `COHERE_API_KEY` is unset or the API call fails, `rerank_chunks()` returns the top-N RRF results unchanged. The system continues to function with hybrid-without-reranking quality — never hard-failing due to an optional enhancement.

**Trade-offs**

- Adds approximately 150–250ms latency and per-query API cost. This is partially offset by the reduction in LLM context size — fewer, higher-quality chunks mean fewer input tokens charged by the LLM provider.

---

## 3. Elasticsearch for Sparse Retrieval

**Context**

A BM25 index needs to support: fast query-time search, efficient bulk ingestion, and targeted deletion by `user_id` or `document_id`.

**Decision**

Use **Elasticsearch 8.x** as the BM25 search engine.

**Reasoning**

- Native, well-tuned BM25 implementation with no configuration required.
- `delete_by_query` enables efficient bulk deletion scoped to any field — removing all chunks for a user or a specific document is a single API call that does not require tracking individual document IDs.
- The `elasticsearch-py` client is mature, well-documented, and actively maintained.
- Single-node Docker Compose deployment is adequate for development; the same setup scales horizontally for production without application changes.

**Single shared index with field-level isolation**

Rather than one index per user (which would complicate cluster management at scale), all chunks share a single `rag_chunks` index. Every search query carries a `filter: term: user_id` clause, providing logical isolation at query time. Elasticsearch's inverted index architecture handles this efficiently — filtered queries do not scan other users' documents.

**Alternative considered**

An in-process BM25 library such as `rank-bm25`. Rejected because it cannot persist state across process restarts, cannot scale beyond a single instance, and does not support targeted deletion.

---

## 4. Qdrant for Dense Retrieval

**Context**

A vector database needs to support: high-dimensional nearest-neighbour search, per-user storage isolation, and efficient bulk deletion.

**Decision**

Use **Qdrant** with per-user collections (`user_<id>`).

**Reasoning**

- Purpose-built for approximate nearest-neighbour (ANN) search on dense vectors, with strong performance on high-dimensional cosine similarity queries.
- The `payload` feature allows arbitrary metadata to be stored alongside each vector, so a single query returns the chunk text and provenance data needed to build the context window — no secondary lookup required.
- Cloud-hosted option (Qdrant Cloud) removes the need to manage the ANN index infrastructure.

**Per-user collections vs. shared collection with payload filtering**

Per-user collections provide **hard storage isolation**: a query issued to `user_<alice>` structurally cannot touch `user_<bob>`'s vectors. Deleting a user's data is a single `delete_collection` call. With a shared collection, deletion would require `delete_by_payload` — a slower operation that scans the collection and is more error-prone under concurrent workloads.

**Alternatives considered**

- **pgvector** (PostgreSQL extension): convenient (reuses Supabase), but significantly slower than Qdrant for collections above ~100K vectors, and lacks the ANN index options that Qdrant provides.
- **Pinecone**: managed and mature, but higher cost at scale and less flexible payload support.

---

## 5. Embedding Model: all-MiniLM-L6-v2 via fastembed

**Context**

Both ingestion and query require text-to-vector embedding. The model must be consistent across both contexts, fast enough to run synchronously (with thread offloading), and free to run without a GPU.

**Decision**

Use **`sentence-transformers/all-MiniLM-L6-v2`** via the **fastembed** library.

**Reasoning**

fastembed is a lightweight, pure-Python embedding library that avoids the PyTorch and CUDA runtime dependencies required by HuggingFace's `sentence-transformers` library. This has practical consequences:

- The Docker image is significantly smaller and faster to build.
- Container startup time is reduced (no PyTorch initialisation).
- The deployment environment is simpler — no CUDA driver or GPU is required.

The embedding logic is centralised in `config/embeddings.py` and shared between ingestion and query. This is a deliberate architectural constraint: any change to the model must be reflected in both contexts simultaneously, preventing the silent corruption that occurs when ingestion and retrieval use different embedding spaces.

**Model selection rationale**

- 384-dimensional output keeps Qdrant storage costs and ANN search latency low.
- Strong performance on semantic textual similarity benchmarks for its parameter count.
- Zero per-embedding API cost.

**Trade-offs**

- The model runs in-process, consuming approximately 90 MB of memory. For deployments requiring very high query throughput, the embedding step would benefit from extraction into a dedicated microservice.

---

## 6. Per-User Storage Isolation

**Context**

The system serves multiple independent users whose data must never be accessible to one another — at rest, in transit, and during query execution.

**Decision**

Scope all data by the authenticated user's UUID (`user_id` derived from the Supabase Auth JWT). Enforce isolation at every storage layer independently.

**Enforcement layers**

| Layer | Mechanism |
|-------|-----------|
| Qdrant | Per-user collection naming (`user_<id>`) — structural impossibility of cross-user queries |
| Elasticsearch | `filter: term: user_id` on every search query; `user_id` scoped on every deletion |
| Supabase | `user_id` columns on `docs`, `chunks`, and `conversations`; ownership checks before mutations |
| Application | `delete_document` verifies ownership before proceeding; conversation endpoints verify ownership on every read and write |

**Why UUID over numeric tenant ID**

The previous version of this system used a numeric `tenant_id`. The migration to user UUID as the primary key eliminates a mapping layer and uses the natural identifier from the auth provider — the same ID that is present in every JWT and every Supabase table.

---

## 7. Chunking Strategy

**Context**

Documents must be split into chunks small enough to embed meaningfully and fit within LLM context windows, while remaining large enough to provide useful context for answering questions.

**Decision**

`RecursiveCharacterTextSplitter` with `chunk_size=1000` characters and `chunk_overlap=200` characters.

**Reasoning**

The recursive splitter attempts to break text at natural language boundaries (`\n\n` → `\n` → `.` → ` `) before resorting to arbitrary character-level splits. This preserves semantic coherence within chunks, which directly improves embedding quality and retrieval precision.

1,000 characters (approximately 200 tokens) provides enough context for a meaningful embedding while staying well within the practical limit for retrieval chunks. 200 characters of overlap ensures that sentences straddling a chunk boundary appear in both adjacent chunks, preventing retrieval from missing an answer located near a split point.

**Alternative considered**

Token-based chunking (splitting by model token count rather than character count) would more precisely control what each model sees. The added complexity of a tokenizer dependency was not warranted for the current use case.

---

## 8. PDF Extraction with OCR Fallback

**Context**

Users upload both text-native PDFs (the common case) and image-based scanned documents (less common but legitimate). Silently failing on scanned PDFs would create a confusing user experience.

**Decision**

Attempt `PyPDFLoader` first. If every extracted page is empty, fall back to Tesseract OCR via `pdf2image` and OpenCV.

**Reasoning**

- Text-native PDFs: `PyPDFLoader` is fast, accurate, and dependency-free.
- Scanned PDFs: Without OCR, these produce zero-length content and are marked `failed`. The fallback captures them with reasonable accuracy.
- OpenCV preprocessing (grayscale conversion and binary thresholding) is standard document processing practice and measurably improves Tesseract accuracy on low-contrast or noisy scans.

**Trade-offs**

OCR is slow (several seconds per page for dense text) and introduces system-level dependencies (`tesseract-ocr`, `poppler-utils`), both of which are installed in the Dockerfile. For high-volume use cases, OCR processing should be moved to a background task queue to avoid blocking the request thread.

---

## 9. Dual Indexing on Ingestion

**Context**

Hybrid retrieval requires two indexes to stay in sync: the Qdrant dense vector collection and the Elasticsearch BM25 index. A document that is indexed in one but not the other produces asymmetric retrieval results.

**Decision**

Write to both indexes synchronously within a single ingestion call, with coordinated rollback if either write fails.

**Reasoning**

Synchronous dual-writing is the simplest approach that guarantees consistency — if the ingestion call returns success, both indexes contain the document. The rollback strategy is explicit: if any write fails after vectors have already been committed to Qdrant, those vectors are deleted and the Elasticsearch entries are removed by query.

**Trade-offs**

The ingestion call blocks until all three writes (Qdrant, Elasticsearch, Supabase) complete. For large documents with hundreds of chunks, this can take tens of seconds. The correct long-term solution is to move ingestion to an asynchronous task queue (e.g., Celery or ARQ), returning an ingestion ID immediately and allowing the client to poll for completion.

---

## 10. Cost-Aware LLM Routing with Circuit Breaker

**Context**

Routing all queries to the same large LLM is wasteful — a simple factual question does not justify the latency or cost of a 120B-parameter model. Additionally, LLM providers experience occasional outages and latency spikes that must not cascade into degraded service for all users.

**Decision**

Implement a `ModelRouter` that: (1) selects the cheapest healthy model that meets quality requirements, and (2) maintains a per-model circuit breaker based on rolling error rate and p99 latency.

**Routing logic**

1. Classify the query's complexity using the intent classifier.
2. If the query is simple, route to the `fast` model tier.
3. Otherwise, walk the fallback chain: `primary → fast → fallback`.
4. Skip any model whose circuit is open.

**Circuit breaker thresholds**

- **Error rate > 5%** over a rolling 100-call window → circuit opens
- **p99 latency > 3,000ms** → circuit opens
- **Cooldown period:** 60 seconds before entering half-open state

**Why in-process rather than a dedicated circuit breaker service**

For a single-server deployment, in-process state is sufficient and has zero infrastructure overhead. The acknowledged limitation is that circuit breaker state is not shared across multiple instances. The documented path forward is to persist health counters to Redis.

---

## 11. LLM-Based Intent Classification

**Context**

The routing decision requires a signal about query complexity. The signal must generalise to arbitrary query phrasing — a keyword list or length heuristic would be too brittle.

**Decision**

Use `llama-3.1-8b-instant` via Groq as a binary classifier: `True` = simple factual query, `False` = complex multi-step query.

**Reasoning**

An LLM-based classifier generalises to arbitrary phrasing by construction. "What does TCP stand for?" and "Explain the TCP three-way handshake in detail" are classified differently not by word count or keyword rules, but by semantic understanding of what each question requires.

Using the fastest, cheapest model (~200ms, minimal cost) keeps the classification overhead acceptable. Every classification is logged to the `intent` table, creating a dataset for evaluating classifier accuracy and fine-tuning routing thresholds without deploying code changes.

---

## 12. OpenRouter as Fallback Provider

**Context**

The system needs a fallback LLM from a different provider than the primary (Groq) to ensure resilience against provider-level outages. The fallback should be available at zero or minimal cost.

**Decision**

Use **OpenRouter** as the fallback provider, specifically `google/gemma-4-31b-it:free`.

**Reasoning**

- OpenRouter exposes multiple model providers through a single OpenAI-compatible API interface, accessible via `langchain_openai.ChatOpenAI` with a custom `base_url`.
- The free-tier Gemma model provides genuine provider-level redundancy at no additional cost.
- A different provider (OpenRouter/Google vs. Groq) means that a Groq outage does not affect fallback availability.

---

## 13. Supabase for Auth and Relational Data

**Context**

The system requires user authentication and a structured store for document metadata, chunk registries, conversation threads, and message history. The previous version maintained a direct PostgreSQL connection via SQLAlchemy alongside Supabase for Auth — a split that added unnecessary complexity.

**Decision**

Consolidate on **Supabase** for both authentication and all relational data, accessed exclusively via the Supabase REST client.

**Reasoning**

Removing the direct PostgreSQL connection eliminates:
- SSL certificate management and `sslrootcert` configuration
- SQLAlchemy ORM model definitions and migration management
- `SessionLocal`, `get_db()` dependency injection, and per-request session lifecycle management

The Supabase REST client provides a clean, typed interface for the CRUD operations this system performs. All tables benefit from Row Level Security policies that can be applied at the database level, independently of application logic.

**Trade-offs**

The Supabase REST API adds one network hop compared to a direct database connection. For bulk insert operations (e.g., inserting hundreds of chunk rows during ingestion), this overhead is measurable. At current scale, the operational simplicity justifies this cost.

---

## 14. Conversation Threading

**Context**

Users interact with the system through sequences of related questions. Without threading, each query is isolated — there is no way to group related exchanges, name a session, or retrieve conversation history.

**Decision**

Add `conversations` and `messages` tables to Supabase with full CRUD endpoints, and auto-create a conversation for every `POST /query` call that does not provide a `conversation_id`.

**Reasoning**

Auto-creation removes friction: users can start querying immediately without an explicit "create conversation" step. The first 80 characters of the query become the conversation title, providing a meaningful label. Users who want to manage their sessions explicitly can use the `POST /conversations` endpoint.

All conversation data is scoped by `user_id` at the database level, making cross-user access structurally impossible regardless of application-layer bugs.

---

## 15. Global JWT Middleware

**Context**

The previous version used an `X-API-KEY` header to protect document ingestion routes and had no authentication on the query endpoint. This created an inconsistent security model: some routes used API keys, others used JWTs, and some had no protection at all.

**Decision**

Remove per-route API key enforcement. Apply a **single global JWT middleware** that validates a Supabase Bearer token on every non-public path.

**Reasoning**

- **Uniform security model:** every client, whether human or machine-to-machine, uses the same authentication mechanism.
- **Correct ownership semantics:** user identity is derived from the cryptographically signed JWT, not from a client-supplied parameter. A user can only access data scoped to their own UUID.
- **Single point of enforcement:** authentication logic exists in exactly one place. A bug or improvement affects all routes simultaneously, eliminating the possibility of accidentally shipping an unprotected endpoint.

**Public paths** (explicitly opted out): `/`, `/health`, all `/auth/*` routes, `/docs`, `/redoc`, `/openapi.json`.

---

## 16. User-Scoped Semantic Cache

**Context**

The previous cache key was `sha256(query_text)`. This meant that two different users asking the same question — "what is the refund policy?" — would share a single cache entry. The second user would receive the cached answer derived from the *first user's* documents, regardless of relevance.

**Decision**

Change the cache key to `sha256(f"{user_id}:{query_text}")`.

**Reasoning**

This was a correctness bug, not merely a potential issue. Each user's document set is unique. The answer to any question is only valid in the context of the specific documents from which it was derived. Scoping the key by user ID ensures that cache hits are always returning the right answer to the right user.

---

## 17. Lazy Client Initialisation

**Context**

The Supabase and Qdrant clients require environment variables that may not be set in all environments. Instantiating them at module import time causes unhelpful errors at startup.

**Decision**

Wrap both clients in a `LazyClient` that defers initialisation until the first attribute access, using `@cached_property` to ensure the factory is invoked exactly once.

**Reasoning**

- Errors from missing configuration are raised at the point of first use, with a clear traceback pointing to the missing variable — not at import time with a confusing `NameError`.
- A temporarily unavailable external service at startup does not prevent the server from starting. Routes that do not require that specific client (e.g., auth routes when Qdrant is briefly unavailable) continue to function.
- `@cached_property` guarantees that the client is constructed once and then reused for the lifetime of the process, consistent with connection pooling expectations.

---

## 18. Bulk Document Upload

**Context**

Users frequently need to seed a new project with multiple documents. Requiring them to issue one HTTP request per file creates unnecessary friction and multiplies round-trip overhead.

**Decision**

Add `POST /add_docs` that accepts up to 10 files per request, processed sequentially with per-file error isolation.

**Reasoning**

Sequential processing is preferable to concurrent for this operation:
- The embedding model runs in-process and is not thread-safe to call concurrently from multiple goroutines.
- Sequential processing produces predictable, bounded memory usage regardless of how many files are in the batch.
- Per-file error isolation means a corrupted or non-PDF file in the batch does not abort the processing of other files — the caller receives a complete result with per-file status.

The 10-file limit prevents a single request from monopolising the server for an unbounded duration.

---

## 19. Opt-In Timing Instrumentation

**Context**

The query pipeline spans multiple I/O stages: embedding, BM25 search, dense search, RRF, reranking, and LLM invocation. Diagnosing latency regressions requires stage-level visibility. However, always-on logging would add noise in production and create a performance overhead that is difficult to quantify.

**Decision**

Implement per-stage timing via `timed_stage` (sync) and `async_timed_stage` (async) context managers, enabled only when `APP_ENV ∈ {dev, development, local}` or `ENABLE_TIMING=true`.

**Reasoning**

Context managers make the instrumentation declaration site visible at every measured operation. The implementation is a no-op when timing is disabled — `timing_enabled()` returns `False` and the context manager yields immediately with no overhead. When enabled, a `request_id` is propagated through every stage for correlation across the full pipeline trace.

This design provides deep observability on demand without burdening production traffic.

---

## 20. Grounded Prompt Design

**Context**

LLMs have a strong prior from pretraining that causes them to supplement retrieved context with general world knowledge. For a document Q&A system, this behaviour produces confident, plausible-sounding answers that may be completely unrelated to the user's documents.

**Decision**

The system prompt explicitly and repeatedly prohibits the model from using prior knowledge, and mandates the exact response `"I don't have that information."` when the retrieved context does not contain an answer.

**Reasoning**

In professional document retrieval use cases — contracts, compliance policies, financial reports — a hallucinated answer is strictly worse than no answer. Users rely on the system to surface what their documents actually say, not what the LLM believes to be generally true. Strict grounding makes every response auditable: if the answer exists, it is attributable to a retrieved chunk; if it does not exist, the system says so.

---

## 21. Input Guardrails and PII Masking

**Context**

User-provided text is sent to a third-party LLM API. Two categories of risk must be addressed: (1) prompt injection attempts that try to override the system prompt and manipulate model behaviour, and (2) sensitive personal data that should not be transmitted to external APIs.

**Decision**

Pre-process every query with a deterministic, regex-based guardrail layer that detects injection patterns and masks high-risk PII before any external call is made.

**Why regex over an LLM-based guard**

An LLM-based guardrail (e.g., calling a separate safety model before the main LLM) adds a full network round-trip to every query. Regex runs in microseconds, adds zero API cost, is fully deterministic, and is auditable by inspection. For the threat model of this system, regex coverage of known attack patterns is the appropriate starting point.

**Two-tier PII response**

- **High-risk PII** (SSNs, credit card numbers): Redacted and replaced with a placeholder token before the text is sent to the LLM API or stored in the cache. Transmitting this data to a third-party API is a data privacy violation regardless of the query's intent.
- **Lower-risk PII** (email addresses, phone numbers): Detected and logged but not redacted, as these may represent legitimate search context (e.g., querying for records associated with a specific email address).

---

## 22. Planned Improvements

The following items represent known limitations and prioritised future work:

| Area | Current State | Planned Improvement |
|------|--------------|---------------------|
| **Async ingestion** | PDF processing blocks the request thread for large documents | Extract to a background task queue (Celery, ARQ); return an ingestion ID immediately with a polling endpoint |
| **OCR latency** | Multi-page OCR can take 30+ seconds | Run OCR asynchronously; expose `status: processing` to the client |
| **Token budget enforcement** | `TokenTracker` is fully implemented but not wired into the query pipeline | Connect to `run_query()` to enforce configurable per-user daily token budgets |
| **Multi-instance circuit breaker** | Circuit breaker state is in-process, not shared across server instances | Migrate health counters to Redis for correctness in horizontally scaled deployments |
| **Cache invalidation** | Cache relies on TTL expiry only | Add event-driven invalidation when a user's document set changes |
| **Streaming responses** | LLM response is buffered until fully generated | Implement Server-Sent Events for real-time token streaming on long responses |
| **Conversation context in prompt** | `prompt_builder` accepts a `memory` parameter but it is not populated | Inject recent conversation turns into the prompt to enable multi-turn coherence |
| **Hallucination blocking** | Hallucination signals are logged as warnings but do not block responses | Add a configurable `risk_score` threshold above which `OutputValidationError` is raised |
| **Configurable reranker** | Reranker model is hardcoded to `rerank-v4.0-fast` | Surface reranker model choice in `config.yaml` alongside LLM models |
