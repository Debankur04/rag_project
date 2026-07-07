# Architecture & Design Decisions

This document explains the key architectural and technical decisions made in the RAG Backend. For each decision, it covers the context (what problem was being solved), the choice made, and the reasoning behind it.

---

## Table of Contents

1. [Multi-Tenancy Model](#1-multi-tenancy-model)
2. [Vector Database: Qdrant](#2-vector-database-qdrant)
3. [Embedding Model: all-MiniLM-L6-v2](#3-embedding-model-all-minilm-l6-v2)
4. [Chunking Strategy](#4-chunking-strategy)
5. [PDF Extraction with OCR Fallback](#5-pdf-extraction-with-ocr-fallback)
6. [LLM Model Routing](#6-llm-model-routing)
7. [Intent Classification for Routing](#7-intent-classification-for-routing)
8. [Circuit Breaker Pattern](#8-circuit-breaker-pattern)
9. [Authentication: Supabase](#9-authentication-supabase)
10. [Relational Metadata Store: PostgreSQL](#10-relational-metadata-store-postgresql)
11. [Semantic Query Cache: Redis](#11-semantic-query-cache-redis)
12. [Operational Logging: MongoDB](#12-operational-logging-mongodb)
13. [Guardrails: Prompt Injection and PII](#13-guardrails-prompt-injection-and-pii)
14. [Output Validation](#14-output-validation)
15. [Grounded Prompt Design](#15-grounded-prompt-design)
16. [Duplicate Document Detection via Content Hash](#16-duplicate-document-detection-via-content-hash)
17. [Lazy Client Initialization](#17-lazy-client-initialization)
18. [Framework: FastAPI](#18-framework-fastapi)
19. [Rate Limiting on the Query Endpoint](#19-rate-limiting-on-the-query-endpoint)
20. [Known Gaps and Future Improvements](#20-known-gaps-and-future-improvements)

---

## 1. Multi-Tenancy Model

**Context:** The system needs to serve multiple independent tenants whose documents and queries must never cross-contaminate.

**Decision:** Use a **per-tenant Qdrant collection** model (`tenant_<id>`), and scope all PostgreSQL records (`doc`, `chunks`) by a numeric `tenant_id` column.

**Why:**

- **Hard data isolation at the storage layer.** Qdrant collection boundaries ensure one tenant's vectors can never appear in another tenant's search results, even under bugs or misrouted requests.
- **Simple mental model.** Every query is `collection_name=tenant_<id>`, which is self-evidently correct.
- **Independent scalability.** High-volume tenants can be migrated to a dedicated Qdrant node without affecting others.
- **Straightforward deletion.** Deleting a tenant means dropping a Qdrant collection and filtering SQL records by `tenant_id` — no complex joins or cascade rules.

**Trade-off:** Collection-per-tenant increases the number of Qdrant collections as the tenant count grows. This is acceptable at current scale (Qdrant supports thousands of collections) but would need review at very high tenant counts. An alternative (shared collection with metadata filtering) would require payload-based filtering, which is slower and more error-prone.

---

## 2. Vector Database: Qdrant

**Context:** The system needs a vector store capable of fast approximate nearest-neighbor (ANN) search to find semantically relevant chunks for a query.

**Decision:** Use **Qdrant** as the vector database.

**Why:**

- **Purpose-built for vector search.** Qdrant is designed from the ground up for this use case, with strong performance on cosine similarity queries.
- **Rich payload support.** Each vector point can carry structured metadata (`document_id`, `source`, `chunk_index`, `text`), enabling filtering and context retrieval in a single call.
- **Cloud-hosted option.** Qdrant Cloud provides a managed cluster, removing the need to self-manage an ANN index.
- **Python client.** First-class `qdrant-client` Python library with both sync and async support.
- **Collection-level operations.** The ability to create, query, and drop entire collections aligns perfectly with the per-tenant isolation model.

**Alternatives considered:**

- **Pinecone** — managed, but significantly more expensive at scale and less flexible payload support.
- **pgvector (PostgreSQL extension)** — convenient (reuses existing PostgreSQL), but much slower than Qdrant for large vector sets and lacks advanced filtering.
- **FAISS** — fast but in-memory only; no persistence, no cloud option.

---

## 3. Embedding Model: all-MiniLM-L6-v2

**Context:** Chunks and queries need to be converted to dense vectors for semantic search.

**Decision:** Use **`all-MiniLM-L6-v2`** from Sentence-Transformers via `langchain-huggingface`.

**Why:**

- **No API cost.** The model runs locally (or on the same server). There are no per-request charges for embedding, unlike OpenAI embeddings.
- **High quality for its size.** On the SBERT benchmarks, `all-MiniLM-L6-v2` punches well above its weight for semantic similarity tasks.
- **384 dimensions.** Small enough to keep Qdrant storage costs low and search latency minimal.
- **Deterministic.** The same text always produces the same vector, which is critical for semantic caching (the query cache key is derived from the text hash, and the search uses the same embedding space).

**Trade-off:** Running the model in-process adds memory overhead (~90 MB). For high-throughput deployments, this model would be deployed as a separate embedding microservice.

**Consistency note:** The same model is used for both ingestion and queries. This is mandatory — if the models ever diverge, retrieval quality collapses.

---

## 4. Chunking Strategy

**Context:** LLMs have context window limits. Documents must be split into manageable pieces. The split strategy directly affects retrieval quality.

**Decision:** Use **`RecursiveCharacterTextSplitter`** with `chunk_size=1000`, `chunk_overlap=200`.

**Why:**

- **Recursive splitting preserves semantic boundaries.** The splitter first tries to break on `\n\n` (paragraph), then `\n` (line), then `.`, then ` ` (word), before falling back to character-level splits. This produces more semantically coherent chunks than a naive fixed-size split.
- **1000 characters** is a practical balance between:
  - Enough context for the LLM to generate a useful answer.
  - Small enough to keep embedding quality high (too-long chunks dilute semantic signal).
- **200 characters of overlap** prevents information loss at chunk boundaries. A sentence that straddles a boundary appears in both neighboring chunks, so retrieval won't miss it.

**Alternative considered:** **Token-based chunking.** Splitting by tokens (rather than characters) more precisely controls what the LLM sees. However, character-based splitting avoids a tokenizer dependency and is easier to reason about at configuration time.

---

## 5. PDF Extraction with OCR Fallback

**Context:** PDFs come in two types: text-native (the common case) and image-based scans (legacy documents, photocopied contracts).

**Decision:** Use **PyPDF for primary extraction**, fall back to **Tesseract OCR via pdf2image and OpenCV** for image-only PDFs.

**Why:**

- **Text-native PDFs:** PyPDF is fast, pure Python, and produces accurate text without any image processing.
- **Image-only PDFs:** Without OCR, these documents would fail silently and be marked as containing no content. OCR expands the range of ingestible documents significantly.
- **OpenCV preprocessing:** Converting to grayscale and applying binary thresholding improves Tesseract accuracy on low-contrast or noisy scans — this is standard practice in document processing pipelines.

**Trade-off:** OCR is slow (multiple seconds per page) and adds system dependencies (`tesseract`, `poppler`). This is acceptable because ingestion is an offline operation. Future work could offload OCR to a background task queue (Celery/Redis Queue).

---

## 6. LLM Model Routing

**Context:** Using a single expensive LLM for all queries is wasteful. Simple questions do not require a 70B-parameter model.

**Decision:** Implement a **configurable model router** driven by `config.yaml`, with three tiers:

| Tier | Model | Use case |
|------|-------|---------|
| `fast` | `llama-3.1-8b-instant` (Groq) | Simple, factual, low-complexity queries |
| `primary` | `llama-3.3-70b-versatile` (Groq) | Complex, multi-step, reasoning-heavy queries |
| `fallback` | `gemini-2.0-flash` (Google) | Failover when Groq is down |

**Why:**

- **Cost reduction.** The fast model costs approximately 10× less than the primary. Routing even 50% of simple queries to it meaningfully reduces LLM spend.
- **Latency reduction.** The fast model responds in ~200ms vs. ~850ms for the primary. Cache-miss simple queries feel instant.
- **Multi-provider resilience.** Having both Groq and Google as providers ensures the system keeps working even if one provider has an outage.

**Configuration-driven design:**

Routing rules live in `config.yaml`, not in source code. This means model tiers, cost parameters, latency thresholds, and the fallback chain can be adjusted without a deployment.

---

## 7. Intent Classification for Routing

**Context:** Routing decisions need a signal about query complexity.

**Decision:** Use an **LLM-based binary intent classifier** (`llama-3.1-8b-instant`) to classify queries as `simple` (True) or `complex` (False).

**Why:**

- **LLM classifiers generalize well.** A classifier prompt is far more flexible than a keyword list. It understands semantics — `"what does TCP stand for?"` is correctly classified as simple; `"design a microservices architecture for an e-commerce platform"` is correctly classified as complex.
- **Zero additional infrastructure.** The classifier reuses an existing Groq client, so there's no additional service to maintain.
- **Logged for improvement.** All classifications are written to the `intent` table. This creates a dataset for fine-tuning or evaluating the classifier over time.

**Trade-off:** The classifier itself adds ~200ms of latency on every cache miss. This is acceptable because: (a) it uses the fastest available model, and (b) it only runs when the result is not cached.

**Alternative considered:** Rule-based classification (e.g., query length, keyword presence). Rejected because it's brittle and requires constant maintenance as query patterns evolve.

---

## 8. Circuit Breaker Pattern

**Context:** LLM providers occasionally experience elevated error rates or latency spikes. Without protection, these issues cascade into all user-facing queries.

**Decision:** Implement a **circuit breaker** in the `ModelRouter` that temporarily removes unhealthy models from the rotation.

**Thresholds:**

- **Error rate** > 5% (over a rolling 100-call window)
- **p99 latency** > 3000ms

**Behavior:**

- When thresholds are crossed, the model's circuit opens for **60 seconds**.
- After 60 seconds, the circuit enters "half-open" state and allows the next call through as a test.
- If successful, the circuit closes. If not, it opens again.

**Why:**

- **Fail fast.** An open circuit immediately routes requests to the next model in the fallback chain, preventing a slow or failing model from dragging down response times.
- **Self-healing.** The half-open state allows automatic recovery without operator intervention.
- **Per-model tracking.** Each model has independent health tracking. A Groq outage doesn't affect the Gemini fallback.

---

## 9. Authentication: Supabase

**Context:** The system needs user registration, login, JWT issuance, refresh, and password reset without building a custom auth service.

**Decision:** Use **Supabase Auth** as the identity provider.

**Why:**

- **Batteries included.** Supabase provides email/password auth, JWT issuance, token refresh, and password reset emails out of the box.
- **No custom auth infrastructure.** Building a secure auth system (salted hashing, token rotation, email delivery) takes significant time and has many attack vectors. Delegating to a proven service reduces risk.
- **Standard JWTs.** Supabase tokens are standard JWTs and can be verified by any service that has access to the public key, enabling future microservice expansion.
- **Service role key.** The `SUPABASE_SERVICE_ROLE_KEY` allows backend operations to bypass Row Level Security when needed, without exposing the anon key.

**Trade-off:** Supabase is an external dependency. If Supabase is unavailable, auth operations fail. The mitigation is that data (documents, vectors, logs) is stored in systems the project controls. Auth failure does not cause data loss.

---

## 10. Relational Metadata Store: PostgreSQL

**Context:** Document and chunk metadata needs durable, queryable storage with support for transactions, foreign keys, and status updates.

**Decision:** Use **PostgreSQL** for all structured metadata (`doc`, `chunks`, `intent` tables).

**Why:**

- **ACID guarantees.** Document status transitions (pending → processing → ingested → failed) need to be atomic and durable. A NoSQL store would require manual consistency management.
- **Foreign keys.** The `chunks.document_id → doc.id` relationship is enforced at the database level, preventing orphaned chunk records.
- **Rich query support.** Filtering documents by tenant, status, and content hash in a single query is trivial with SQL.
- **Supabase integration.** The project already depends on Supabase, which provides a hosted PostgreSQL instance. Reusing the same infrastructure reduces operational overhead.

**SSL configuration:**

The connection enforces `sslmode=verify-full` with a root certificate, ensuring connections to the production database are encrypted and authenticated.

---

## 11. Semantic Query Cache: Redis

**Context:** Repeated queries (common in production) should not invoke the LLM every time.

**Decision:** Cache query results in **Redis**, keyed by a **SHA-256 hash of the query text**.

**Why SHA-256, not the raw text:**

- Uniform key length regardless of query length.
- Safe for use as a Redis key (no special characters).
- Deterministic — the same query always maps to the same key.

**Why Redis:**

- **Sub-millisecond reads.** Redis lookups add ~1ms to response time.
- **TTL support.** Keys expire automatically without any background cleanup jobs.
- **Used for rate limiting too.** Redis is already in the stack for `RateLimitMiddleware`, so adding a cache does not introduce a new dependency.

**TTL:** 600 seconds (10 minutes) by default. Configurable via `CACHE_TTL_SECONDS`.

**Current limitation:** Cache keys are not scoped to `tenant_id`. Two different tenants asking the same question would share a cache entry. This is a known gap — see [Known Gaps](#20-known-gaps-and-future-improvements).

---

## 12. Operational Logging: MongoDB

**Context:** The system needs an audit trail of ingestion and query events for debugging, monitoring, and model evaluation.

**Decision:** Use **MongoDB** for append-only operational logs.

**Why:**

- **Schema flexibility.** Log payloads vary in structure (different models return different token usage shapes, guardrail metadata varies per query). MongoDB handles this without migrations.
- **Append-only pattern.** Logs are never updated, only inserted. MongoDB is well-optimized for this.
- **No foreign key constraints needed.** Logs reference `query_id` or `ingestion_id` for correlation, but no referential integrity is required.
- **Async writes.** Using `motor` (Motor async driver), log writes are non-blocking and do not add latency to the query response path.

**Motor over PyMongo (async):**

Synchronous database writes in an async FastAPI handler would block the event loop. Using `AsyncIOMotorClient` for log writes keeps the event loop free for concurrent requests.

---

## 13. Guardrails: Prompt Injection and PII

**Context:** User-provided text is sent to an LLM. Malicious inputs can attempt to override the system prompt, extract confidential information, or bypass the grounding rules.

**Decision:** Implement a **pre-processing guardrails layer** that:

1. Detects prompt injection patterns using regex.
2. Masks high-risk PII before it reaches the LLM or gets cached.

**Why regex over an LLM-based guard:**

- **Zero latency cost.** Regex runs in microseconds.
- **No API call.** An LLM-based guardrail (e.g., NVIDIA NeMo Guardrails) adds a round trip to every query.
- **Deterministic.** Regex rules are auditable and testable. An LLM-based guard can fail inconsistently.

**PII masking strategy:**

- **Credit cards and SSNs** are redacted (`[REDACTED_SSN]`) because sending them to a third-party LLM API is a data privacy violation.
- **Emails and phone numbers** are detected but not redacted, as they may be legitimate query context (e.g., "What did user@company.com submit?").

**Risk score:**

Injections produce a numeric risk score. Currently this score is logged. Future work could add a block threshold (e.g., refuse queries with `risk_score > 5`).

---

## 14. Output Validation

**Context:** LLMs can produce malformed, truncated, repetitive, or hallucinated responses.

**Decision:** Validate every LLM response before returning it to the client.

**Checks:**

1. **Minimum length (15 words)** — filters out empty or truncated responses.
2. **Repetition ratio (< 30% unique words)** — detects stuck loops.
3. **Hallucination patterns** — logs overconfident phrases for review.

**Why:** These are cheap string operations that catch the most common LLM failure modes. They complement (rather than replace) prompt-based instructions to stay grounded.

---

## 15. Grounded Prompt Design

**Context:** RAG systems that don't constrain the LLM will blend retrieved context with the model's prior knowledge, producing confident but unverifiable answers.

**Decision:** The system prompt **explicitly forbids** the LLM from using prior knowledge, guessing, or inferring. The only permitted answer sources are the retrieved chunks.

```
You MUST answer strictly and only using the information provided
in the GROUND TRUTH CONTEXT section.
- Do NOT use prior knowledge.
- Do NOT guess or infer.
- If the answer is not explicitly stated, respond: "I don't have that information."
```

**Why this matters:**

In enterprise document retrieval (legal, financial, compliance), a hallucinated answer is worse than no answer. Forcing the LLM to defer when context is absent builds user trust and makes the system auditable.

---

## 16. Duplicate Document Detection via Content Hash

**Context:** Tenants may accidentally re-upload the same document. Without de-duplication, this creates redundant chunks, inflates vector store size, and degrades retrieval precision.

**Decision:** Compute a **SHA-256 hash of the file content** before ingestion. If a hash match exists (with status `ingested` and existing chunks), skip ingestion.

**Why SHA-256:**

- **Content-addressed.** Even if the file is renamed, the same content is detected as a duplicate.
- **Fast.** SHA-256 is computed in milliseconds for typical document sizes.

**Why also verify chunk existence:**

A document marked `ingested` may have had its chunks deleted externally. The hash check alone would incorrectly block re-ingestion. The system validates that chunks actually exist, and if not, resets the status to `failed` and allows re-ingestion.

---

## 17. Lazy Client Initialization

**Context:** FastAPI starts before all environment variables are guaranteed to be loaded. Instantiating Supabase and Qdrant clients at import time can fail silently or with confusing errors.

**Decision:** Wrap Supabase and Qdrant clients in a **`LazyClient`** that instantiates the underlying client on first attribute access, not at import time.

```python
class LazyClient:
    def __init__(self, factory):
        self._factory = factory

    @cached_property
    def _client(self):
        return self._factory()

    def __getattr__(self, name):
        return getattr(self._client, name)
```

**Why:**

- **Cleaner startup errors.** If `QDRANT_URL` is missing, the error is raised when a request is made, not at server start — with a clear message and traceback.
- **No eager initialization.** If, for example, Qdrant is temporarily down at startup, the server still starts and can serve auth and cached query requests.

---

## 18. Framework: FastAPI

**Context:** The system needs a production-grade Python web framework.

**Decision:** Use **FastAPI**.

**Why:**

- **Async-first.** LLM calls, Redis lookups, and Qdrant queries are all I/O-bound. FastAPI's async support allows the event loop to serve concurrent requests while waiting on I/O.
- **Automatic OpenAPI/Swagger.** Documentation is generated from Pydantic models at zero additional cost.
- **Pydantic validation.** Request body parsing and validation is declarative and type-safe.
- **Dependency injection.** `Depends(get_db)` cleanly injects database sessions into route handlers without global state.
- **Lifespan hooks.** `@asynccontextmanager async def lifespan(app)` provides clean startup hooks for database initialization.

---

## 19. Rate Limiting on the Query Endpoint

**Context:** The query endpoint calls an LLM on every cache miss. Abuse or runaway clients could exhaust LLM API quotas or incur unexpected costs.

**Decision:** Apply **IP-based rate limiting** exclusively to `POST /query` using Redis.

**Why Redis over in-process state:**

- In-process rate limiting doesn't work across multiple server instances.
- Redis `INCR` + `EXPIRE` is atomic, race-condition-free, and already in the stack.

**Why IP-based rather than user-based:**

The query endpoint does not currently require authentication. IP-based limiting is the only available signal. When user authentication is added to the query endpoint, the rate limit key should migrate to `user_id` for more precise enforcement.

---

## 20. Known Gaps and Future Improvements

The following items represent intentional trade-offs or deferred work:

| Area | Current State | Recommended Improvement |
|------|--------------|------------------------|
| **Auth on query/ingestion routes** | `POST /query` and `/add_doc` are not authenticated per user | Add Bearer token verification to enforce per-user access control |
| **Query cache scoped to tenant** | Cache key is `sha256(query_text)` only — not scoped by `tenant_id` | Change key to `sha256(f"{tenant_id}:{query_text}")` |
| **Token budget enforcement** | `TokenTracker` class is fully implemented but not wired into the query pipeline | Connect `TokenTracker` to `run_query()` and enforce `DAILY_BUDGET_USD` per user tier |
| **APIKeyMiddleware not applied** | `APIKeyMiddleware` is defined but not registered in `main.py` | Register it in the `middleware` list in `main.py` |
| **Background ingestion** | PDF ingestion is synchronous on the request thread | Move to a task queue (Celery + Redis) to support large documents without HTTP timeouts |
| **Hallucination block threshold** | Hallucination patterns are logged but don't block responses | Add a configurable threshold to raise `OutputValidationError` on high-risk outputs |
| **Intent classifier import path** | `model_router.py` imports `from llmops.intent_classifier` (missing `query.` prefix) | Fix to `from query.llmops.intent_classifier import IntentClassifier` |
| **Observability** | No metrics endpoint | Add Prometheus metrics (request count, latency p99, cache hit rate, model selection frequency) |
| **Streaming responses** | LLM responses are returned only after fully generated | Implement Server-Sent Events or WebSocket streaming for long responses |
