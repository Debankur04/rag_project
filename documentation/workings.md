# How It Works

This document explains the inner workings of the RAG Backend API. It walks through the ingestion pipeline, the query pipeline, and all supporting subsystems — from document chunking to model routing to caching.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Document Ingestion Pipeline](#2-document-ingestion-pipeline)
   - [Flow](#flow)
   - [PDF Text Extraction](#pdf-text-extraction)
   - [Chunking Strategy](#chunking-strategy)
   - [Embedding](#embedding)
   - [Vector Storage](#vector-storage)
   - [Metadata Persistence](#metadata-persistence)
   - [Duplicate Detection](#duplicate-detection)
3. [Query Pipeline](#3-query-pipeline)
   - [Flow](#flow-1)
   - [Semantic Caching](#semantic-caching)
   - [Guardrails — Input Sanitization](#guardrails--input-sanitization)
   - [Embedding](#embedding-1)
   - [Vector Search](#vector-search)
   - [Intent Classification](#intent-classification)
   - [Model Routing](#model-routing)
   - [Prompt Engineering](#prompt-engineering)
   - [LLM Invocation](#llm-invocation)
   - [Guardrails — Output Validation](#guardrails--output-validation)
   - [Caching and Logging](#caching-and-logging)
4. [Authentication](#4-authentication)
5. [Middleware](#5-middleware)
   - [Rate Limiting](#rate-limiting)
   - [API Key Middleware](#api-key-middleware)
6. [Database Architecture](#6-database-architecture)
   - [PostgreSQL](#postgresql)
   - [Qdrant](#qdrant)
   - [Redis](#redis)
   - [MongoDB](#mongodb)
7. [Configuration](#7-configuration)
8. [Observability](#8-observability)

---

## 1. System Overview

The RAG Backend is a **multi-tenant Retrieval-Augmented Generation (RAG)** service. It allows each tenant to:

- **Ingest PDF documents** that are chunked, embedded, and stored in a per-tenant vector collection.
- **Query those documents** using natural language. Relevant chunks are retrieved and sent to an LLM to generate grounded answers.

The system enforces strict **grounding rules**: the LLM is only permitted to answer from the retrieved context. If the answer is not present, it returns `"I don't have that information."` This prevents hallucination and ensures that responses are traceable to ingested source material.

Key design pillars:

- **Multi-tenancy**: All data is scoped by `tenant_id`. Tenants are fully isolated.
- **Safety**: Guardrails detect prompt injection, PII, and unsafe output before/after the LLM.
- **Cost awareness**: An intent classifier routes simple queries to cheap models and reserves expensive models for complex requests.
- **Observability**: All ingestion and query events are logged to MongoDB with full token usage and status.

---

## 2. Document Ingestion Pipeline

### Flow

```
Client uploads PDF
       ↓
POST /add_doc (tenant_id, file)
       ↓
1. Compute SHA-256 hash of file content
2. Check if document already ingested (de-duplication)
       ↓ (if duplicate)
       Return existing document record
       ↓ (if new)
3. Create Document record with status="pending"
4. Update status to "processing"
       ↓
5. Extract text (PyPDF → fallback to OCR if no text layers)
6. Chunk text (RecursiveCharacterTextSplitter)
7. Generate embeddings for each chunk (all-MiniLM-L6-v2)
       ↓
8. Create or ensure Qdrant collection exists: tenant_<id>
9. Upsert vector points to Qdrant
10. Bulk insert Chunk records into PostgreSQL
       ↓
11. Update Document status to "ingested"
12. Log ingestion event to MongoDB
       ↓
Return document metadata and chunk count
```

### PDF Text Extraction

**Primary method:** `PyPDFLoader` from LangChain Community.

If `PyPDFLoader` returns empty pages (i.e., the PDF is an image-based scan), the system falls back to **OCR**:

1. Convert PDF pages to images using `pdf2image.convert_from_path()`.
2. Preprocess each page with OpenCV (grayscale, thresholding) to improve OCR accuracy.
3. Extract text using `pytesseract.image_to_string()`.

This two-tier approach handles both text-native PDFs and scanned documents.

### Chunking Strategy

**Splitter:** `RecursiveCharacterTextSplitter` from LangChain.

**Parameters:**

- `chunk_size = 1000` characters
- `chunk_overlap = 200` characters

**Why recursive?** The splitter tries to break text at natural boundaries (paragraphs, sentences) before falling back to character-level splits. This preserves semantic coherence within chunks.

**Chunk metadata:**

- `document_id`
- `source` (file name)
- `chunk_index` (0-based position in the document)
- `text` (the chunk content itself)

### Embedding

All chunks are embedded using **`all-MiniLM-L6-v2`** from HuggingFace.

- **Dimensionality:** 384
- **Distance metric:** Cosine similarity
- **Model type:** Sentence-Transformers (optimized for semantic similarity)

This model is lightweight, fast, and produces high-quality embeddings suitable for retrieval tasks.

### Vector Storage

Vectors are stored in **Qdrant**, a production-grade vector database optimized for high-speed nearest-neighbor search.

**Collection naming:** Each tenant gets a dedicated collection: `tenant_<tenant_id>`.

**Point structure:**

```python
{
  "id": "uuid-string",
  "vector": [0.123, -0.456, ...],  # 384-dim embedding
  "payload": {
    "document_id": int,
    "source": "filename.pdf",
    "chunk_index": int,
    "text": "chunk content"
  }
}
```

**Collection initialization:**

If the collection doesn't exist, it's created on-the-fly with:

```python
VectorParams(size=384, distance=Distance.COSINE)
```

### Metadata Persistence

**PostgreSQL tables:**

1. **`doc`** (Document)
   - `id` (BigInt, primary key)
   - `tenant_id` (BigInt, indexed)
   - `filename` (String)
   - `url` (String, source reference)
   - `content_hash` (SHA-256, indexed for duplicate detection)
   - `status` (String: `pending`, `processing`, `ingested`, `failed`, `deleted`)
   - `created_at`, `updated_at` (timestamps)

2. **`chunks`** (Chunk)
   - `id` (UUID, primary key)
   - `document_id` (BigInt, foreign key to `doc.id`)
   - `tenant_id` (BigInt, indexed)
   - `vector_id` (String, references the Qdrant point ID)
   - `chunk_index` (Integer)
   - `created_at` (timestamp)

These tables enable:

- Efficient lookups by tenant
- Document status tracking (e.g., retry failed ingestions)
- Mapping between SQL records and Qdrant vectors for deletions

### Duplicate Detection

Before ingesting a new document, the system computes a **SHA-256 hash** of the file content.

It then queries:

```sql
SELECT * FROM doc
WHERE tenant_id = :tenant_id
  AND content_hash = :hash
  AND status = 'ingested'
```

If a match is found **and** the document has associated chunks in the `chunks` table, the system skips ingestion and returns the existing record with `duplicate: true`.

This prevents redundant processing and storage costs.

### Error Handling and Rollback

If any step fails after vector insertion:

1. The system attempts to delete all inserted Qdrant points using `points_selector=PointIdsList(points=inserted_vector_ids)`.
2. The `Document` status is set to `"failed"`.
3. A descriptive error is returned to the caller.

This ensures that partial ingestions do not pollute the vector store.

---

## 3. Query Pipeline

### Flow

```
Client sends natural language query
       ↓
POST /query (text, tenant_id)
       ↓
1. Generate cache key (SHA-256 of query text)
2. Check Redis cache
       ↓ (if cached)
       Return cached answer immediately
       ↓ (if not cached)
3. Sanitize input (guardrails)
       - Detect prompt injection patterns
       - Mask high-risk PII (SSN, credit card)
       - Calculate risk score
       ↓
4. Embed query text (all-MiniLM-L6-v2)
       ↓
5. Search tenant's Qdrant collection (top-5 chunks)
       ↓
6. Classify intent (simple vs. complex)
       ↓
7. Route to appropriate model (cheap for simple, expensive for complex)
       ↓
8. Build grounded prompt with retrieved context
       ↓
9. Invoke LLM (async, with latency tracking)
       ↓
10. Validate output (length, repetition, hallucination signals)
       ↓
11. Cache result and log to MongoDB
       ↓
Return answer and token usage
```

### Semantic Caching

**Cache key:** SHA-256 hash of the normalized query text.  
**Storage:** Redis  
**TTL:** Configurable via `CACHE_TTL_SECONDS` (default: 600 seconds = 10 minutes)

When a query arrives:

```python
key = f"query_cache:{sha256(text)}"
cached = redis.get(key)
if cached:
    return json.loads(cached)
```

Cache hits skip embedding, vector search, and LLM invocation entirely. This dramatically reduces latency and cost for repeated queries.

**Cache invalidation:**

There is currently no automatic invalidation on document updates. The cache relies on TTL expiration. Future work could add event-driven invalidation when a tenant's documents are modified.

### Guardrails — Input Sanitization

All incoming queries pass through a **sanitization layer** before processing:

#### Threat Detection

**Prompt injection patterns:**

```regex
- r"ignore (previous|all) instructions" (high severity)
- r"you are now" (medium)
- r"pretend (you are|to be)" (medium)
- r"jailbreak" (high)
- r"DAN mode" (high)
- r"forget your (system|instructions)" (high)
```

**HTML/script injection:**

```regex
- r"<\s*(script|iframe|object)[^>]*>"
```

Each match increments a risk score. High-severity patterns contribute +3, medium +1.

**Embedded prompt-like instructions:**

If more than 2 occurrences of patterns like `"you are"`, `"act as"`, or `"system prompt"` are detected, the input is flagged as likely prompt injection.

#### PII Masking

**Detected patterns:**

- `credit_card`: `\b(?:\d[ -]*?){13,16}\b`
- `ssn`: `\b\d{3}-\d{2}-\d{4}\b`
- `passport`: `\b[A-Z]{1,2}\d{6,9}\b`
- `email`: `\b[\w\.-]+@[\w\.-]+\.\w+\b`
- `phone`: `\b\d{10}\b`

**Masking strategy:**

- **High-risk** (credit cards, SSNs): Replaced with `[REDACTED_CREDIT_CARD]` or `[REDACTED_SSN]`.
- **Low-risk** (emails, phones): Detected and logged in metadata but **not masked** (as they may be necessary for context).

#### Text Normalization

All text is:

- Converted to lowercase.
- Collapsed to single spaces (`\s+` → ` `).
- Stripped of leading/trailing whitespace.

This produces a "clean" text suitable for embedding and a "normalized" text for consistent cache key generation.

### Embedding

The sanitized query text is embedded using the same model as documents: **`all-MiniLM-L6-v2`**.

This ensures query embeddings live in the same vector space as document chunks, enabling accurate retrieval.

### Vector Search

The query embedding is sent to Qdrant:

```python
qdrant.query_points(
    collection_name=f"tenant_{tenant_id}",
    query=embedding,
    limit=5
)
```

**Returns:** The top-5 most similar chunks (by cosine similarity).

Each result includes:

- `payload["text"]`: The chunk content.
- `payload["source"]`: Original document name.
- `payload["chunk_index"]`: Position in the document.

**If no results are returned** (e.g., the tenant has no documents), the query is sent directly to the LLM without context. The LLM responds using its pretrained knowledge, but the system prompt still instructs it to avoid hallucination.

### Intent Classification

The system uses a **fast LLM-based intent classifier** to determine query complexity.

**Model:** `llama-3.1-8b-instant` (via Groq)

**Prompt:**

```
You are an intent classifier. Return strictly 'True' if the user query
is a simple factual question or greeting (e.g., asking for weather, definitions).
Return strictly 'False' if it is a complex query requiring multi-step planning,
reasoning, or external data processing (e.g., travel planning, complex searches).
Output nothing else but True or False.
```

**Classification result:**

- `True` → route to **fast model** (cheap, low-latency)
- `False` → route to **primary model** (expensive, high-quality)

**Intent logging:**

All classifications are stored in the PostgreSQL `intent` table for analysis and classifier tuning.

```sql
CREATE TABLE intent (
  id UUID PRIMARY KEY,
  query TEXT,
  intent TEXT  -- 'simple' or 'complex'
);
```

### Model Routing

The **ModelRouter** selects the best model based on:

1. **Intent classification** (simple vs. complex).
2. **Model health** (error rate, latency, circuit breaker state).

**Routing rules (from `config.yaml`):**

```yaml
routing_rules:
  use_intent_classifier: true
  simple_query_model: fast
  default_model: primary
  fallback_chain: [primary, fast, fallback]
  latency_threshold_ms: 3000
  error_threshold_pct: 5
```

**Fallback chain:**

1. **primary** — `llama-3.3-70b-versatile` (Groq)
2. **fast** — `llama-3.1-8b-instant` (Groq)
3. **fallback** — `gemini-2.0-flash` (Google)

**Health tracking:**

Each model maintains a `ModelHealth` object:

- **`error_count`** / **`total_calls`** → error rate
- **`latencies`** (rolling window of last 100 calls) → p99 latency
- **`circuit_open`** — if error rate > 5% or p99 > 3000ms, the circuit opens for 60 seconds

**Circuit breaker behavior:**

When a circuit is open, the model is considered unhealthy and skipped in the fallback chain. After the cooldown period (60 seconds), the circuit enters a "half-open" state and allows one test call.

### Prompt Engineering

The system uses a **grounded prompt template** designed to minimize hallucination.

```python
SYSTEM_RULES = """
You are an information retrieval assistant.

You MUST answer strictly and only using the information provided
in the GROUND TRUTH CONTEXT section.

Rules you must follow:
- Do NOT use prior knowledge.
- Do NOT guess or infer.
- Do NOT add details not present in the context.
- If the answer is not explicitly stated, respond exactly with:
  "I don't have that information."
"""

prompt = f"""
SYSTEM RULES:
{SYSTEM_RULES}

GROUND TRUTH CONTEXT:
{context}

USER QUERY:
{query}
"""
```

**Context assembly:**

```python
context = "\n\n".join(chunk.payload["text"] for chunk in top_5_results)
```

If no chunks are retrieved, `{{context}}` is replaced with an empty string, and the LLM is instructed to refuse answering.

### LLM Invocation

The router invokes the selected model asynchronously:

```python
client = router.get_client(model_key)
response = await client.ainvoke(prompt)
```

**Token tracking:**

Token usage is extracted from the response metadata:

```python
input_tokens = response.usage_metadata["input_tokens"]
output_tokens = response.usage_metadata["output_tokens"]
```

These values are logged and could be used for billing or budget enforcement.

**Latency tracking:**

Elapsed time is measured and recorded:

```python
start = time.time()
response = await client.ainvoke(...)
latency_ms = (time.time() - start) * 1000
router.record_success(model_key, latency_ms)
```

This feeds into the p99 latency calculation for circuit breaker decisions.

### Guardrails — Output Validation

After the LLM returns a response, the output is validated:

#### Length Check

```python
word_count = len(output.split())
if word_count < 15:
    raise OutputValidationError("Reply too short")
```

This filters out truncated or incomplete responses.

#### Repetition Check

```python
unique_words = len(set(output.split()))
if unique_words < word_count * 0.3:
    raise OutputValidationError("Too repetitive (possible LLM failure)")
```

If fewer than 30% of words are unique, the response is likely a failure mode (e.g., the model got stuck in a loop).

#### Hallucination Signals

The validator scans for overconfident or unrealistic claims:

```regex
- r"\$\d{4,}"           # Large dollar amounts
- r"guaranteed price"
- r"confirmed booking"
- r"100% success"
- r"no risk"
- r"as of \d{4}"        # Specific year claims
- "definitely", "always"
```

These patterns don't block the response but are logged as warnings for review.

### Caching and Logging

Once validation passes:

1. **Cache the result** in Redis (keyed by query hash, TTL = 600s).
2. **Log to MongoDB** via `log_query_async()`:

```python
{
  "query_id": "uuid",
  "query_text": "...",
  "response": {
    "answer": "...",
    "token_usage": {...}
  },
  "intent": "simple" | "complex" | null,
  "status": "success" | "cached" | "error",
  "timestamp": datetime.utcnow()
}
```

This creates an audit trail for every query.

---

## 4. Authentication

Authentication is handled by **Supabase Auth**.

**Flow:**

1. Client calls `POST /auth/register` or `POST /auth/login`.
2. The backend proxies the request to Supabase using the `supabase-py` client.
3. Supabase returns a JWT (`access_token`) and a `refresh_token`.
4. The client includes the JWT in the `Authorization: Bearer <token>` header for protected routes.

**Protected routes:**

- `POST /auth/logout`
- `GET /auth/verify`

**Token verification:**

```python
user = supabase.auth.get_user(token)
```

If the token is invalid or expired, a `401 Unauthorized` error is returned.

**Refresh flow:**

Clients call `POST /auth/refresh` with their `refresh_token` to obtain a new `access_token`.

**Password reset:**

1. Client calls `POST /auth/forgot-password` with an email.
2. Supabase sends a reset email containing a one-time `access_token`.
3. Client calls `POST /auth/reset-password` with the token and new password.

---

## 5. Middleware

### Rate Limiting

**Implementation:** `RateLimitMiddleware` (applied globally)

**Target:** Only `POST /query` requests.

**Algorithm:**

```python
key = f"rate_limit:{client_ip}"
current = redis.incr(key)
if current == 1:
    redis.expire(key, RATE_LIMIT_WINDOW_SECONDS)
if current > RATE_LIMIT_REQUESTS:
    raise HTTPException(status_code=429)
```

**Defaults:**

- `RATE_LIMIT_REQUESTS = 10`
- `RATE_LIMIT_WINDOW_SECONDS = 60`

**Scope:** Per IP address.

**Bypass:** Non-query routes are not rate-limited.

### API Key Middleware

**Implementation:** `APIKeyMiddleware` (doc_ingestion module)

**Purpose:** Restrict document ingestion endpoints to trusted backend services (e.g., a Java microservice).

**Header:** `X-API-KEY: <value>`

**Validation:**

```python
server_key = os.getenv("JAVA_BACKEND_API_KEY")
client_key = request.headers.get("X-API-KEY")
if client_key != server_key:
    return 401 Unauthorized
```

**Exempted routes:**

- `/`, `/health`, `/docs`, `/openapi.json`

---

## 6. Database Architecture

The system uses **four databases**, each optimized for a specific purpose.

### PostgreSQL

**Role:** Relational metadata store.

**Tables:**

1. **`doc`** — Document records
2. **`chunks`** — Chunk metadata (links to Qdrant vectors)
3. **`intent`** — Intent classification logs

**ORM:** SQLAlchemy (declarative models)

**Connection pool:**

```python
engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "verify-full", "sslrootcert": "certs/prod-ca-2021.crt"},
    pool_pre_ping=True,
    pool_recycle=3600
)
```

**Session management:**

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Qdrant

**Role:** Vector database for embeddings and nearest-neighbor search.

**Client:**

```python
qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
```

**Per-tenant collections:**

Each tenant's vectors are isolated in a dedicated collection: `tenant_<tenant_id>`.

**Vector config:**

```python
VectorParams(size=384, distance=Distance.COSINE)
```

**Search API:**

```python
qdrant.query_points(
    collection_name="tenant_42",
    query=[...],
    limit=5
)
```

### Redis

**Role:** Cache and rate limiter.

**Client:**

```python
redis = redis.from_url(REDIS_URL, decode_responses=True)
```

**Use cases:**

1. **Semantic query cache** — stores query results keyed by SHA-256 hash.
2. **Rate limiting** — tracks request counts per IP with TTL.

**Asynchronous operations:**

Redis is accessed asynchronously in query endpoints using the `redis.asyncio` client.

### MongoDB

**Role:** Append-only operational logs (audit trail).

**Collections:**

1. **`ingestion_logs`** — document upload events
2. **`query_logs`** — query invocations with full context

**Client:**

```python
mongo_async_client = AsyncIOMotorClient(MONGO_URI)
mongo_async_db = mongo_async_client[MONGO_DB]
```

**Log schema (query_logs):**

```json
{
  "query_id": "uuid",
  "query_text": "What is the capital of France?",
  "response": {
    "answer": "Paris.",
    "token_usage": {...}
  },
  "intent": "simple",
  "status": "success",
  "timestamp": "2026-07-07T10:15:30Z"
}
```

---

## 7. Configuration

**Primary config file:** `config/config.yaml`

**Model definitions:**

```yaml
models:
  primary:
    provider: groq
    model_name: llama-3.3-70b-versatile
    max_tokens: 4096
    cost_per_1k_input: 0.0006
    cost_per_1k_output: 0.0008
    avg_latency_ms: 850
    tier: expensive
```

**Routing rules:**

```yaml
routing_rules:
  use_intent_classifier: true
  simple_query_model: fast
  default_model: primary
  fallback_chain: [primary, fast, fallback]
```

**Environment overrides:**

All secrets and endpoint URLs are loaded from `.env` using Pydantic Settings:

```python
class Settings(BaseSettings):
    GROQ_API_KEY: str | None = None
    REDIS_URL: str = "redis://localhost:6379/0"
    ...
    model_config = SettingsConfigDict(env_file=".env")
```

---

## 8. Observability

### Logs

The system writes structured logs to:

1. **Console (stdout)** — FastAPI request logs, error traces.
2. **MongoDB** — Ingestion and query event logs.

### Metrics (Future)

Token usage, latency, and error rates are tracked in-memory by the `ModelRouter`. These could be exported to:

- **Prometheus** (via `/metrics` endpoint)
- **CloudWatch** / **Datadog** (via agent)

### Trace IDs

Every query generates a unique `query_id` (UUID). This ID appears in:

- The API response
- MongoDB logs
- Console logs

This enables full request tracing across all systems.
