# RAG Backend - Documentation

Welcome to the documentation hub for the **RAG Backend API** - a production-oriented, multi-tenant Retrieval-Augmented Generation (RAG) service built with FastAPI.

---

## What is this project?

This backend enables any tenant to:

1. **Ingest PDF documents** into a per-tenant vector store.
2. **Query those documents** using natural language, backed by LLM-generated answers grounded strictly in the ingested content.
3. **Manage authentication** (register, login, token refresh, password reset) via Supabase Auth.

The system is designed to be safe, cost-aware, and observable - with rate limiting, semantic caching, guardrails, model routing, and structured logging baked in.

---

## Documentation Structure

| File | What it covers |
|------|---------------|
| [api.md](documentation/api.md) | All HTTP endpoints - methods, paths, request/response schemas, auth requirements, error codes |
| [workings.md](documentation/workings.md) | How the system works end-to-end - ingestion pipeline, query pipeline, embedding, vector search, LLM calls, caching, and logging |
| [decisions.md](documentation/decisions.md) | Architectural and technical decisions - why specific databases, models, chunking strategies, and design patterns were chosen |

---

## Quick Start

### Prerequisites

| Dependency | Purpose |
|-----------|---------|
| Python >= 3.11 | Runtime |
| PostgreSQL | Relational metadata store (documents, chunks, intents) |
| Qdrant | Vector database for per-tenant embeddings |
| Redis | Semantic query cache + rate limiting |
| MongoDB | Append-only operational logs (ingestion + query) |
| Supabase | Auth provider (JWT issuance and verification) |

### Environment Variables

Create a `.env` file in the project root:

```env
# Supabase
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=<anon-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>

# Qdrant
QDRANT_URL=https://<host>:6333
QDRANT_API_KEY=<key>

# Redis
REDIS_URL=redis://localhost:6379/0
CACHE_TTL_SECONDS=600
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW_SECONDS=60

# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB=rag

# LLM providers
GROQ_API_KEY=<key>
GEMINI_API_KEY=<key>

# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=<password>
DB_SSLMODE=verify-full
DB_SSLROOTCERT=certs/prod-ca-2021.crt

# Internal API key (for machine-to-machine calls to doc_ingestion routes)
JAVA_BACKEND_API_KEY=<key>
```

### Running the Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.  
Interactive docs (Swagger UI) are served at `http://localhost:8000/docs`.

---

## Architecture at a Glance

```
+------------------------------------------------------------------+
¦                        FastAPI Application                        ¦
¦                                                                    ¦
¦  +------------+   +-------------------+   +--------------------+ ¦
¦  ¦  /auth/*   ¦   ¦  /add_doc         ¦   ¦  /query            ¦ ¦
¦  ¦  Supabase  ¦   ¦  /delete_doc      ¦   ¦  Cache ? Embed     ¦ ¦
¦  ¦  JWT Auth  ¦   ¦  /delete_tenant   ¦   ¦  ? Qdrant Search   ¦ ¦
¦  +------------+   +-------------------+   ¦  ? LLM ? Validate  ¦ ¦
¦                                            +--------------------+ ¦
+------------------------------------------------------------------¦
¦  Middleware: RateLimitMiddleware (Redis) ¦ APIKeyMiddleware       ¦
+------------------------------------------------------------------¦
¦  Data Stores                                                       ¦
¦  PostgreSQL (metadata) ¦ Qdrant (vectors) ¦ Redis ¦ MongoDB (logs)¦
+------------------------------------------------------------------+
```

---

## Module Overview

```
rag_project/
+-- main.py                  # FastAPI app entry point, lifespan hooks, middleware
+-- config/
¦   +-- settings.py          # Pydantic Settings - all env vars
¦   +-- config.yaml          # LLM model definitions and routing rules
¦   +-- db.py                # Lazy Supabase + Qdrant client wrappers
¦   +-- db_config.py         # SQLAlchemy engine, session factory, get_db()
+-- auth/                    # Authentication module (Supabase-backed)
¦   +-- controllers/         # Route handlers
¦   +-- services/            # Business logic (register, login, refresh, etc.)
¦   +-- dto/                 # Pydantic request/response models
+-- doc_ingestion/           # Document ingestion module
¦   +-- controllers/         # Route handlers
¦   +-- services/            # PDF reading, chunking, embedding, Qdrant upsert
¦   +-- models/              # SQLAlchemy ORM models (Document, Chunk)
¦   +-- middleware/          # APIKeyMiddleware
¦   +-- dto/                 # Request/response schemas
+-- query/                   # Query module
    +-- controllers/         # Route handlers
    +-- services/            # Cache, query orchestration, prompt building, logging
    +-- llmops/              # ModelRouter, IntentClassifier, Guardrails, TokenTracker
    +-- models/              # Intent ORM model
    +-- middleware/          # RateLimitMiddleware
    +-- dto/                 # Request/response schemas
```

---

## Key Design Principles

- **Multi-tenancy**: Every document and vector collection is scoped to a `tenant_id`. Tenants are fully isolated at the data layer.
- **Grounded answers**: The LLM is instructed to answer only from retrieved context. It will respond with `"I don't have that information."` if context is absent.
- **Defense in depth**: Rate limiting, input guardrails, PII masking, output validation, and API key middleware all run before/after the LLM.
- **Cost awareness**: An intent classifier routes simple queries to a cheap, fast model and reserves the expensive model for complex queries.
- **Observability**: Every ingestion and query event is logged to MongoDB with status, timing, and token usage.

---

## Further Reading

- [API Reference ?](./api.md)
- [System Workings ?](./workings.md)
- [Architecture Decisions ?](./decisions.md)

---

## Docker Manual Testing

The Compose setup runs three services:

- `app`: FastAPI API on `http://localhost:8000`
- `redis`: Redis 7 on `localhost:6379`
- `elasticsearch`: local Elasticsearch on `localhost:9200`

Build and start everything:

```bash
docker compose up --build
```

Run in the background:

```bash
docker compose up --build -d
```

Check service status:

```bash
docker compose ps
```

Follow API logs:

```bash
docker compose logs -f app
```

Stop services:

```bash
docker compose down
```

Stop services and remove local Redis/Elasticsearch data volumes:

```bash
docker compose down -v
```

Compose overrides these service URLs for the API container:

```env
REDIS_URL=redis://redis:6379/0
ELASTICSEARCH_URL=http://elasticsearch:9200
```

Keep these additional hybrid RAG keys in `.env`:

```env
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_INDEX=rag_chunks
BM25_CANDIDATE_LIMIT=1000
HYBRID_RETRIEVAL_TOP_K=20
HYBRID_RERANK_TOP_K=10
COHERE_API_KEY=
OPENROUTER_API_KEY=
```
