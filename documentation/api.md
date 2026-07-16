# API Reference

Complete HTTP API documentation for the Hybrid RAG Backend.

| | |
|---|---|
| **Base URL** | `http://localhost:8000` |
| **Interactive Docs** | `http://localhost:8000/docs` (Swagger UI, JWT-enabled) |
| **OpenAPI Schema** | `http://localhost:8000/openapi.json` |

---

## Contents

1. [Authentication & Global Conventions](#1-authentication--global-conventions)
2. [System Endpoints](#2-system-endpoints)
3. [Auth — `/auth`](#3-auth----auth)
4. [Document Ingestion](#4-document-ingestion)
5. [Query](#5-query)
6. [Conversations](#6-conversations)
7. [Error Reference](#7-error-reference)

---

## 1. Authentication & Global Conventions

### Bearer Token Authentication

All endpoints except the public paths listed below require a valid **Supabase JWT** passed as a Bearer token:

```
Authorization: Bearer <access_token>
```

Tokens are issued by `POST /auth/login` and `POST /auth/register`. The authenticated user's identity is extracted from the token by the global middleware and injected into `request.state.app_user` — routes never accept a `user_id` parameter, and ownership is always derived from the token.

**Public paths (no token required):**

```
GET  /
GET  /health
POST /auth/register
POST /auth/login
POST /auth/refresh
POST /auth/forgot-password
POST /auth/reset-password
GET  /docs
GET  /redoc
GET  /openapi.json
```

Requests to any other path with a missing or invalid token receive `HTTP 401 Unauthorized`.

### Rate Limiting

`POST /query` is rate-limited per client IP address using Redis atomic counters.

| Setting | Default | Environment Variable |
|---------|---------|---------------------|
| Max requests per window | 10 | `RATE_LIMIT_REQUESTS` |
| Window duration | 60 seconds | `RATE_LIMIT_WINDOW_SECONDS` |
| Response when exceeded | `HTTP 429` | — |

### Content Types

- JSON bodies: `Content-Type: application/json`
- File uploads: `Content-Type: multipart/form-data`

### Error Envelope

All error responses follow a consistent structure:

```json
{
  "detail": "A human-readable description of what went wrong."
}
```

### Request Tracing

Pass an `x-request-id` header to correlate timing logs across pipeline stages. If omitted, the server generates a UUID and returns it in the response header under the same key.

---

## 2. System Endpoints

### `GET /`

Root liveness probe. Returns immediately with no dependencies checked.

**Authentication:** None

**Response `200 OK`**
```json
{ "message": "RAG Backend Running" }
```

---

### `GET /health`

Dependency health check. Verifies Supabase connectivity.

**Authentication:** None

**Response `200 OK`**
```json
{ "status": "ok" }
```

---

## 3. Auth — `/auth`

All authentication flows delegate to **Supabase Auth**, which issues industry-standard JWTs. The backend acts as a thin proxy that forwards credentials to Supabase and normalises the response shape.

---

### `POST /auth/register`

Create a new user account.

**Authentication:** None

**Request Body**
```json
{
  "email": "engineer@example.com",
  "password": "StrongPassword123"
}
```

| Field | Type | Constraints |
|-------|------|-------------|
| `email` | string | Valid RFC 5322 address, 3–320 characters. Normalised to lowercase before processing. |
| `password` | string | 8–128 characters. |

**Response `200 OK`**
```json
{
  "message": "Registration successful. Please check your email if confirmation is enabled.",
  "user": {
    "id": "3f2a1b4c-...",
    "email": "engineer@example.com",
    "created_at": "2026-07-16T10:00:00.000Z"
  },
  "app_user": {
    "id": "3f2a1b4c-...",
    "email": "engineer@example.com",
    "auth_user_id": "3f2a1b4c-..."
  },
  "session": {
    "access_token": "<jwt>",
    "refresh_token": "<opaque-token>",
    "expires_in": 3600,
    "token_type": "bearer",
    "user": { "..." },
    "app_user": { "..." }
  }
}
```

> **Note:** `session` will be `null` when Supabase email confirmation is required. The user must confirm their email before a session is issued.

**Response `400 Bad Request`**
```json
{ "detail": "Unable to register user" }
```

---

### `POST /auth/login`

Authenticate with email and password and receive a session.

**Authentication:** None

**Request Body**
```json
{
  "email": "engineer@example.com",
  "password": "StrongPassword123"
}
```

**Response `200 OK`**
```json
{
  "access_token": "<jwt>",
  "refresh_token": "<opaque-token>",
  "expires_in": 3600,
  "token_type": "bearer",
  "user": {
    "id": "3f2a1b4c-...",
    "email": "engineer@example.com",
    "created_at": "2026-07-16T10:00:00.000Z"
  },
  "app_user": {
    "id": "3f2a1b4c-...",
    "email": "engineer@example.com"
  }
}
```

**Response `401 Unauthorized`**
```json
{ "detail": "Invalid email or password" }
```

---

### `POST /auth/logout`

Invalidate the current session token.

**Authentication:** `Authorization: Bearer <access_token>` *(required)*

**Response `200 OK`**
```json
{ "message": "Logged out" }
```

**Response `401 Unauthorized`**
```json
{ "detail": "Missing bearer token" }
```

---

### `POST /auth/refresh`

Exchange an expired access token for a new one using a refresh token.

**Authentication:** None

**Request Body**
```json
{
  "refresh_token": "<opaque-token>"
}
```

| Field | Constraints |
|-------|-------------|
| `refresh_token` | Minimum 16 characters |

**Response `200 OK`**

Returns a full session payload with the same shape as `POST /auth/login`.

**Response `401 Unauthorized`**
```json
{ "detail": "Invalid refresh token" }
```

---

### `GET /auth/verify`

Verify a bearer token and retrieve the associated user profile.

**Authentication:** `Authorization: Bearer <access_token>` *(required)*

**Response `200 OK`**
```json
{
  "user": {
    "id": "3f2a1b4c-...",
    "email": "engineer@example.com",
    "created_at": "2026-07-16T10:00:00.000Z"
  },
  "app_user": {
    "id": "3f2a1b4c-...",
    "email": "engineer@example.com"
  }
}
```

**Response `401 Unauthorized`**
```json
{ "detail": "Invalid bearer token" }
```

---

### `POST /auth/forgot-password`

Trigger a password reset email to the specified address.

**Authentication:** None

**Request Body**
```json
{ "email": "engineer@example.com" }
```

**Response `200 OK`**
```json
{ "message": "Password reset email sent" }
```

> The response is always `200 OK` regardless of whether the email address exists, to prevent user enumeration.

---

### `POST /auth/reset-password`

Set a new password using the short-lived access token received in the reset email.

**Authentication:** None *(the `access_token` field carries the one-time authorisation)*

**Request Body**
```json
{
  "access_token": "<token-from-reset-email>",
  "password": "NewStrongPassword123"
}
```

| Field | Constraints |
|-------|-------------|
| `access_token` | Minimum 16 characters |
| `password` | 8–128 characters |

**Response `200 OK`**
```json
{ "message": "Password updated" }
```

**Response `401 Unauthorized`**
```json
{ "detail": "Unable to reset password" }
```

---

## 4. Document Ingestion

All document endpoints require a valid Bearer token. The `user_id` is always derived from the JWT — it is never accepted as a request parameter. Each user's documents are isolated in a dedicated Qdrant collection (`user_<id>`) and filtered by `user_id` in the shared Elasticsearch index.

---

### `POST /add_doc`

Upload and ingest a single PDF document.

**Authentication:** Bearer token  
**Content-Type:** `multipart/form-data`

**Form Fields**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | binary (PDF) | Yes | The document to ingest. Only `.pdf` files are accepted. |

**What happens during ingestion:**

1. File is saved to a temporary path and validated.
2. A SHA-256 content hash is computed for duplicate detection.
3. Text is extracted via PyPDF; scanned PDFs fall back to Tesseract OCR with OpenCV preprocessing.
4. Text is split using `RecursiveCharacterTextSplitter` (chunk size: 1,000 chars, overlap: 200 chars).
5. Each chunk is embedded with `all-MiniLM-L6-v2` (384 dimensions).
6. Vectors are upserted into the user's Qdrant collection.
7. Chunks are bulk-indexed into Elasticsearch for BM25 retrieval.
8. Chunk metadata is inserted into Supabase.
9. Document status is updated to `ingested`.

**Example**
```bash
curl -X POST http://localhost:8000/add_doc \
  -H "Authorization: Bearer <token>" \
  -F "file=@/path/to/report.pdf"
```

**Response `200 OK` — Document ingested**
```json
{
  "file_name": "report.pdf",
  "ingestion_id": "a1b2c3d4-...",
  "status": "success",
  "error": null,
  "document": {
    "id": 42,
    "user_id": "3f2a1b4c-...",
    "file_name": "report.pdf",
    "status": "ingested",
    "chunk_count": 47,
    "duplicate": false
  }
}
```

**Response `200 OK` — Duplicate detected**

A document with the same content hash already exists and is fully ingested for this user. Processing is skipped and the existing record is returned.

```json
{
  "file_name": "report.pdf",
  "ingestion_id": "a1b2c3d4-...",
  "status": "success",
  "error": null,
  "document": {
    "id": 42,
    "user_id": "3f2a1b4c-...",
    "file_name": "report.pdf",
    "status": "ingested",
    "duplicate": true
  }
}
```

**Response `400 Bad Request`**
```json
{ "detail": "Only PDF uploads are supported" }
```

**Response `500 Internal Server Error`**

The document record is marked `failed` and all partial writes to Qdrant and Elasticsearch are rolled back atomically.

```json
{ "detail": "No readable content found in PDF" }
```

---

### `POST /add_docs`

Upload and ingest up to 10 PDF documents in a single request.

**Authentication:** Bearer token  
**Content-Type:** `multipart/form-data`

**Form Fields**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `files` | binary[] (PDF) | Yes | One or more PDF files. Maximum 10 per request. |

Each file is processed independently through the same pipeline as `/add_doc`. A failure on one file does not prevent the remaining files from processing.

**Example**
```bash
curl -X POST http://localhost:8000/add_docs \
  -H "Authorization: Bearer <token>" \
  -F "files=@report-q3.pdf" \
  -F "files=@report-q4.pdf"
```

**Response `200 OK`**
```json
{
  "message": "Bulk document ingestion completed",
  "total": 3,
  "success": 2,
  "failed": 1,
  "results": [
    {
      "file_name": "report-q3.pdf",
      "ingestion_id": "a1b2c3d4-...",
      "status": "success",
      "error": null,
      "document": { "id": 43, "chunk_count": 38, "duplicate": false, "..." }
    },
    {
      "file_name": "report-q4.pdf",
      "ingestion_id": "b2c3d4e5-...",
      "status": "success",
      "error": null,
      "document": { "id": 44, "chunk_count": 41, "duplicate": false, "..." }
    },
    {
      "file_name": "presentation.pptx",
      "ingestion_id": null,
      "status": "failed",
      "error": "Only PDF uploads are supported",
      "document": null
    }
  ]
}
```

**Response `400 Bad Request`**
```json
{ "detail": "No files provided. At least one file is required." }
```
```json
{ "detail": "Maximum 10 files per request. Please upload in batches." }
```

---

### `DELETE /delete_doc`

Permanently delete a specific document and all of its associated data.

**Authentication:** Bearer token  
**Content-Type:** `application/json`

Ownership is verified before deletion. Attempting to delete a document that belongs to another user returns `404 Not Found`.

**Request Body**
```json
{
  "doc_id": "42"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `doc_id` | string | The numeric document ID as a string. |

**Deletion is cascaded in this order:**
1. Vectors are deleted from the user's Qdrant collection.
2. Chunks are removed from the Elasticsearch index by `user_id` + `document_id`.
3. Chunk metadata rows are deleted from the Supabase `chunks` table.
4. The document's `status` is set to `"deleted"` in the Supabase `docs` table.

**Response `200 OK`**
```json
{
  "document_id": 42,
  "deleted_chunks": 47,
  "deleted_vectors": 47
}
```

---

### `DELETE /delete_user_data`

Permanently delete all documents, vectors, and chunks belonging to the authenticated user.

**Authentication:** Bearer token

> ⚠️ **This operation is irreversible.** It drops the user's entire Qdrant vector collection, deletes all Elasticsearch chunks, and removes all `docs` and `chunks` rows from Supabase.

**Deletion is cascaded in this order:**
1. The entire `user_<id>` Qdrant collection is dropped.
2. All Elasticsearch chunks for this user are deleted via `delete_by_query`.
3. All Supabase `chunks` rows linked to the user's documents are deleted.
4. All Supabase `docs` rows for the user are deleted.

**Response `200 OK`**
```json
{
  "message": "User documents deleted",
  "result": {
    "user_id": "3f2a1b4c-...",
    "deleted_documents": 5
  }
}
```

---

## 5. Query

### `POST /query`

Submit a natural language query against the authenticated user's ingested documents and receive a grounded, LLM-generated answer.

**Authentication:** Bearer token  
**Rate limit:** 10 requests per 60-second window per IP

**Request Body**
```json
{
  "text": "What are the key risk factors identified in the Q3 financial report?",
  "conversation_id": 7
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | The natural language question. |
| `conversation_id` | integer | No | Attach this query to an existing conversation. If omitted, a new conversation is created automatically, using the first 80 characters of the query as its title. |

**Retrieval Pipeline (on cache miss):**

| Step | Operation |
|------|-----------|
| 1 | Sanitize input — detect prompt injection patterns, mask high-risk PII |
| 2 | Embed query with `all-MiniLM-L6-v2` |
| 3 | BM25 search → top 20 candidates from Elasticsearch |
| 4 | Dense search → top 20 candidates from Qdrant *(steps 3 and 4 run concurrently)* |
| 5 | Reciprocal Rank Fusion → single merged and ranked list |
| 6 | Cohere cross-encoder reranking → top 10 final candidates |
| 7 | Classify query intent → route to appropriate LLM tier |
| 8 | Build grounded prompt, invoke selected model |
| 9 | Validate output (length, repetition, hallucination signals) |
| 10 | Cache result in Redis; persist answer to conversation history |

**Response `200 OK`**
```json
{
  "query_id": "c9d8e7f6-...",
  "conversation_id": 7,
  "answer": "The Q3 report identifies three primary risk factors: currency volatility...",
  "token_usage": {
    "input_tokens": 1248,
    "output_tokens": 312,
    "model": "openai/gpt-oss-120b"
  }
}
```

| Field | Description |
|-------|-------------|
| `query_id` | Unique UUID for this invocation. Useful for log correlation and tracing. |
| `conversation_id` | The conversation this query was appended to. |
| `answer` | The LLM-generated answer, grounded exclusively in retrieved document chunks. |
| `token_usage` | Token consumption and model used. Returns `null` when served from cache. |

**Response `429 Too Many Requests`**
```json
{ "detail": "Rate limit exceeded (10 requests per 60 seconds)" }
```

**Response `500 Internal Server Error`**
```json
{ "detail": "All models unhealthy - serving degraded response" }
```

---

## 6. Conversations

Conversations are persistent threads that group query/answer message pairs. They are stored in Supabase and fully owned by the authenticated user — no conversation data is accessible to other users.

---

### `POST /conversations`

Explicitly create a new conversation with an optional title.

> Note: conversations are also created automatically when `POST /query` is called without a `conversation_id`.

**Authentication:** Bearer token

**Request Body**
```json
{
  "title": "Q3 Risk Analysis"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `title` | string | No | Max 255 characters. Defaults to `"New conversation"` if omitted. |

**Response `200 OK`**
```json
{
  "id": 7,
  "user_id": "3f2a1b4c-...",
  "title": "Q3 Risk Analysis",
  "created_at": "2026-07-16T10:00:00.000Z",
  "updated_at": "2026-07-16T10:00:00.000Z"
}
```

---

### `GET /conversations`

Retrieve all conversations belonging to the authenticated user, ordered by most recently updated.

**Authentication:** Bearer token

**Response `200 OK`**
```json
{
  "conversations": [
    {
      "id": 7,
      "user_id": "3f2a1b4c-...",
      "title": "Q3 Risk Analysis",
      "created_at": "2026-07-16T10:00:00.000Z",
      "updated_at": "2026-07-16T10:48:00.000Z"
    }
  ]
}
```

---

### `GET /conversations/{conversation_id}`

Retrieve a specific conversation along with its full message history, ordered chronologically.

**Authentication:** Bearer token

**Path Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `conversation_id` | integer | The conversation's numeric ID. |

**Response `200 OK`**
```json
{
  "conversation": {
    "id": 7,
    "user_id": "3f2a1b4c-...",
    "title": "Q3 Risk Analysis",
    "created_at": "2026-07-16T10:00:00.000Z",
    "updated_at": "2026-07-16T10:48:00.000Z"
  },
  "messages": [
    {
      "id": 1,
      "conversation_id": 7,
      "role": "user",
      "content": "What are the key risk factors in the Q3 report?",
      "created_at": "2026-07-16T10:01:00.000Z"
    },
    {
      "id": 2,
      "conversation_id": 7,
      "role": "assistant",
      "content": "The Q3 report identifies three primary risk factors...",
      "created_at": "2026-07-16T10:01:03.000Z"
    }
  ]
}
```

**Response `404 Not Found`**
```json
{ "detail": "Conversation not found for current user" }
```

---

### `PATCH /conversations/{conversation_id}`

Rename an existing conversation.

**Authentication:** Bearer token

**Request Body**
```json
{
  "title": "Q3 Financial Risk Deep Dive"
}
```

| Field | Constraints |
|-------|-------------|
| `title` | 1–255 characters, required |

**Response `200 OK`**

Returns the updated conversation object.

**Response `404 Not Found`**
```json
{ "detail": "Conversation not found for current user" }
```

---

### `DELETE /conversations/{conversation_id}`

Delete a conversation and all of its messages.

**Authentication:** Bearer token

**Response `200 OK`**
```json
{
  "conversation_id": 7,
  "status": "deleted"
}
```

**Response `404 Not Found`**
```json
{ "detail": "Conversation not found for current user" }
```

---

## 7. Error Reference

| Status Code | Meaning | Common Triggers |
|-------------|---------|----------------|
| `400 Bad Request` | The request was well-formed but violates a business rule | Non-PDF file upload, more than 10 files in a bulk request, missing required field |
| `401 Unauthorized` | Authentication failed or token is absent | Missing `Authorization` header, expired JWT, invalid credentials on login |
| `404 Not Found` | The resource does not exist or is owned by another user | Accessing a conversation or document that belongs to a different account |
| `422 Unprocessable Entity` | Pydantic validation failure | Field type mismatch, value outside allowed constraints |
| `429 Too Many Requests` | IP-level rate limit exceeded on `POST /query` | More than 10 requests within a 60-second window from the same IP |
| `500 Internal Server Error` | Unhandled server-side failure | All LLM providers unhealthy, PDF extraction failure, storage connectivity issue |
