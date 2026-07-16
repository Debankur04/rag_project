# API Reference

This document is the authoritative reference for all HTTP endpoints exposed by the RAG Backend API. The server is a FastAPI application running under Uvicorn.

**Base URL (local):** `http://localhost:8000`  
**Interactive docs:** `http://localhost:8000/docs` (Swagger UI)  
**OpenAPI schema:** `http://localhost:8000/openapi.json`

---

## Table of Contents

1. [Global Conventions](#1-global-conventions)
2. [System Routes](#2-system-routes)
3. [Authentication — `/auth`](#3-authentication----auth)
   - [POST /auth/register](#post-authregister)
   - [POST /auth/login](#post-authlogin)
   - [POST /auth/logout](#post-authlogout)
   - [POST /auth/refresh](#post-authrefresh)
   - [GET /auth/verify](#get-authverify)
   - [POST /auth/forgot-password](#post-authforgot-password)
   - [POST /auth/reset-password](#post-authreset-password)
4. [Document Ingestion — `/doc_ingestion`](#4-document-ingestion)
   - [POST /add_doc](#post-add_doc)
   - [POST /add_docs](#post-add_docs)
   - [DELETE /delete_doc](#delete-delete_doc)
   - [DELETE /delete_tenant](#delete-delete_tenant)
5. [Query — `/query`](#5-query)
   - [POST /query](#post-query)
6. [Error Reference](#6-error-reference)

---

## 1. Global Conventions

### Content Type

All request bodies are `application/json` unless the endpoint accepts file uploads, in which case the body is `multipart/form-data`.

### Authentication

Routes in the `doc_ingestion` module are protected by an **API Key** passed in the `X-API-KEY` request header. This key is configured server-side via the `JAVA_BACKEND_API_KEY` environment variable and is intended for machine-to-machine calls (e.g., from a Java backend service).

Routes in the `auth` module and the `/query` endpoint do not enforce an API key by default. The `/auth/verify` and `/auth/logout` endpoints require a **Bearer token** in the `Authorization` header.

### Rate Limiting

The `POST /query` endpoint is rate-limited per client IP address using Redis.

- **Default limit:** 10 requests per 60-second window.
- **Configurable via:** `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS` environment variables.
- **Exceeded response:** `HTTP 429` with a descriptive message.

### Response Envelope

All error responses follow this shape:

```json
{
  "detail": "Human-readable error message"
}
```

Success response shapes are endpoint-specific and documented below.

---

## 2. System Routes

### GET /

Health probe. Returns a simple confirmation that the server is running.

**Authentication:** None  
**Rate limited:** No

#### Response `200 OK`

```json
{
  "message": "RAG Backend Running"
}
```

---

### GET /health

Database health check. Verifies that the PostgreSQL connection is live.

**Authentication:** None  
**Rate limited:** No

#### Response `200 OK`

```json
{
  "status": "ok"
}
```

#### Response `503 Service Unavailable`

```json
{
  "detail": "Database connection failed"
}
```

---

## 3. Authentication — `/auth`

All authentication is backed by **Supabase Auth**. Supabase issues standard JWTs. Tokens can be used directly with any Supabase-integrated resource or verified through the `/auth/verify` endpoint.

---

### POST /auth/register

Register a new user account.

**Authentication:** None

#### Request Body

```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `email` | string | Yes | Valid email format, 3–320 characters. Normalized to lowercase. |
| `password` | string | Yes | 8–128 characters. |

#### Response `200 OK`

```json
{
  "message": "Registration successful",
  "user": {
    "id": "uuid-string",
    "email": "user@example.com",
    "created_at": "2026-07-07T10:00:00Z"
  },
  "session": {
    "access_token": "<jwt>",
    "refresh_token": "<token>",
    "expires_in": 3600,
    "token_type": "bearer",
    "user": {
      "id": "uuid-string",
      "email": "user@example.com",
      "created_at": "2026-07-07T10:00:00Z"
    }
  }
}
```

> **Note:** Depending on Supabase email confirmation settings, `session` may be `null` until the user confirms their email.

#### Response `400 Bad Request`

```json
{
  "detail": "Unable to register user"
}
```

---

### POST /auth/login

Authenticate with email and password, returning a session.

**Authentication:** None

#### Request Body

```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `email` | string | Yes | Valid email format. |
| `password` | string | Yes | 1–128 characters. |

#### Response `200 OK`

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<token>",
  "expires_in": 3600,
  "token_type": "bearer",
  "user": {
    "id": "uuid-string",
    "email": "user@example.com",
    "created_at": "2026-07-07T10:00:00Z"
  }
}
```

#### Response `401 Unauthorized`

```json
{
  "detail": "Invalid email or password"
}
```

---

### POST /auth/logout

Invalidate the current session.

**Authentication:** `Authorization: Bearer <access_token>` (required)

#### Request Body

None.

#### Response `200 OK`

```json
{
  "message": "Logged out"
}
```

#### Response `401 Unauthorized`

```json
{
  "detail": "Missing bearer token"
}
```

```json
{
  "detail": "Unable to log out"
}
```

---

### POST /auth/refresh

Exchange a refresh token for a new access token.

**Authentication:** None

#### Request Body

```json
{
  "refresh_token": "<refresh-token>"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `refresh_token` | string | Yes | Minimum 16 characters. |

#### Response `200 OK`

Returns a full session payload identical in shape to the `/auth/login` response.

```json
{
  "access_token": "<new-jwt>",
  "refresh_token": "<new-refresh-token>",
  "expires_in": 3600,
  "token_type": "bearer",
  "user": { ... }
}
```

#### Response `401 Unauthorized`

```json
{
  "detail": "Invalid refresh token"
}
```

---

### GET /auth/verify

Verify that a bearer token is valid and retrieve the associated user.

**Authentication:** `Authorization: Bearer <access_token>` (required)

#### Request Body

None.

#### Response `200 OK`

```json
{
  "user": {
    "id": "uuid-string",
    "email": "user@example.com",
    "created_at": "2026-07-07T10:00:00Z"
  }
}
```

#### Response `401 Unauthorized`

```json
{
  "detail": "Missing bearer token"
}
```

```json
{
  "detail": "Invalid bearer token"
}
```

---

### POST /auth/forgot-password

Trigger a password reset email.

**Authentication:** None

#### Request Body

```json
{
  "email": "user@example.com"
}
```

#### Response `200 OK`

```json
{
  "message": "Password reset email sent"
}
```

#### Response `400 Bad Request`

```json
{
  "detail": "Unable to send password reset email"
}
```

---

### POST /auth/reset-password

Set a new password using the access token received in the reset email.

**Authentication:** None (the `access_token` field carries the authorization)

#### Request Body

```json
{
  "access_token": "<token-from-reset-email>",
  "password": "newSecurePassword123"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `access_token` | string | Yes | Minimum 16 characters. |
| `password` | string | Yes | 8–128 characters. |

#### Response `200 OK`

```json
{
  "message": "Password updated"
}
```

#### Response `401 Unauthorized`

```json
{
  "detail": "Unable to reset password"
}
```

---

## 4. Document Ingestion

All document ingestion endpoints require the `X-API-KEY` header to be set to the value of the `JAVA_BACKEND_API_KEY` environment variable.

```
X-API-KEY: <server-configured-key>
```

Requests that omit or provide an incorrect key will receive `HTTP 401`.

---

### POST /add_doc

Upload and ingest a PDF document for a specific tenant. The document is chunked, embedded, and stored in the tenant's vector collection in Qdrant, with metadata persisted to PostgreSQL.

**Authentication:** `X-API-KEY` header  
**Content-Type:** `multipart/form-data`

#### Request Body (Form Data)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tenant_id` | integer | Yes | The numeric tenant identifier. Scopes the document and its vectors to this tenant. |
| `file` | file (binary) | Yes | The PDF file to ingest. Only `.pdf` files are accepted. |

#### Example (curl)

```bash
curl -X POST http://localhost:8000/add_doc \
  -H "X-API-KEY: your-api-key" \
  -F "tenant_id=42" \
  -F "file=@/path/to/document.pdf"
```

#### Response `200 OK` — New document ingested

```json
{
  "message": "Document ingestion completed",
  "ingestion_id": "uuid-string",
  "status": "success",
  "document": {
    "id": 1,
    "tenant_id": 42,
    "file_name": "document.pdf",
    "status": "ingested",
    "chunk_count": 47,
    "duplicate": false
  }
}
```

#### Response `200 OK` — Duplicate document detected

If a document with the same SHA-256 content hash already exists in an `ingested` state for this tenant, ingestion is skipped and the existing record is returned.

```json
{
  "message": "Document ingestion completed",
  "ingestion_id": "uuid-string",
  "status": "success",
  "document": {
    "id": 1,
    "tenant_id": 42,
    "file_name": "document.pdf",
    "status": "ingested",
    "duplicate": true
  }
}
```

#### Response `400 Bad Request`

```json
{
  "detail": "Only PDF uploads are supported"
}
```

#### Response `401 Unauthorized`

```json
{
  "detail": "Invalid or missing API Key"
}
```

#### Response `500 Internal Server Error`

Returned if text extraction, embedding, or database operations fail. The document record is marked `failed` and any partially written Qdrant vectors are rolled back.

```json
{
  "detail": "No readable content found in PDF"
}
```

---

### POST /add_docs

Upload and ingest **multiple** PDF documents in a single request. Each file is processed independently; failures in one file do not prevent other files from processing.

**Authentication:** Bearer token (from `Authorization` header)  
**Content-Type:** `multipart/form-data`  
**Maximum files per request:** 10

#### Request Body (Form Data)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `files` | file[] (binary) | Yes | Array of PDF files to ingest. Only `.pdf` files are accepted. Minimum 1, maximum 10 files. |

#### Example (curl)

```bash
curl -X POST http://localhost:8000/add_docs \
  -H "Authorization: Bearer <jwt-token>" \
  -F "files=@/path/to/document1.pdf" \
  -F "files=@/path/to/document2.pdf" \
  -F "files=@/path/to/document3.pdf"
```

#### Example (JavaScript/Fetch)

```javascript
const files = document.querySelector('input[type="file"]').files; // Multiple files
const formData = new FormData();

// Add all files to FormData
for (const file of files) {
  formData.append('files', file);
}

const response = await fetch('/add_docs', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`
  },
  body: formData
});

const result = await response.json();
console.log(`Uploaded ${result.success}/${result.total} files successfully`);
```

#### Response `200 OK` — Bulk upload completed

```json
{
  "message": "Bulk document ingestion completed",
  "total": 3,
  "success": 2,
  "failed": 1,
  "results": [
    {
      "file_name": "document1.pdf",
      "ingestion_id": "uuid-string",
      "status": "success",
      "error": null,
      "document": {
        "id": 1,
        "user_id": "user-uuid",
        "file_name": "document1.pdf",
        "status": "ingested",
        "chunk_count": 47,
        "duplicate": false
      }
    },
    {
      "file_name": "document2.pdf",
      "ingestion_id": "uuid-string",
      "status": "success",
      "error": null,
      "document": {
        "id": 2,
        "user_id": "user-uuid",
        "file_name": "document2.pdf",
        "status": "ingested",
        "chunk_count": 23,
        "duplicate": false
      }
    },
    {
      "file_name": "image.png",
      "ingestion_id": null,
      "status": "failed",
      "error": "Only PDF uploads are supported",
      "document": null
    }
  ]
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `message` | string | Confirmation message. |
| `total` | integer | Total number of files processed. |
| `success` | integer | Number of files successfully ingested. |
| `failed` | integer | Number of files that failed. |
| `results` | array | Array of result objects, one per file. See below. |

**Per-File Result Object:**

| Field | Type | Description |
|-------|------|-------------|
| `file_name` | string | Name of the uploaded file. |
| `ingestion_id` | string \| null | UUID of the ingestion attempt (null if failed). |
| `status` | string | Either `"success"` or `"failed"`. |
| `error` | string \| null | Error message (null if successful). |
| `document` | object \| null | Document metadata (null if failed). Same shape as `/add_doc` response. |

#### Response `400 Bad Request`

Returned if:
- No files are provided: `"No files provided. At least one file is required."`
- More than 10 files: `"Maximum 10 files per request. Please upload in batches."`
- Any file is not a PDF: `"Only PDF uploads are supported"` (file marked failed in results, others processed)

```json
{
  "detail": "Maximum 10 files per request. Please upload in batches."
}
```

#### Response `401 Unauthorized`

```json
{
  "detail": "Invalid or missing authentication token"
}
```

#### Response `500 Internal Server Error`

Returned if a file fails during text extraction, embedding, or database operations. The file is marked `failed` in the results, but other files continue processing.

```json
{
  "message": "Bulk document ingestion completed",
  "total": 3,
  "success": 1,
  "failed": 2,
  "results": [
    { "status": "success", ... },
    {
      "file_name": "corrupted.pdf",
      "status": "failed",
      "error": "No readable content found in PDF",
      "document": null
    }
  ]
}
```

---

### DELETE /delete_doc

Delete a specific document and all of its associated vector chunks.

**Authentication:** `X-API-KEY` header  
**Content-Type:** `application/json`

#### Request Body

```json
{
  "tenant_id": 42,
  "doc_id": "1"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tenant_id` | integer | Yes | Owning tenant of the document. |
| `doc_id` | string | Yes | The document's numeric ID (as a string). |

#### Deletion Cascade

1. Qdrant vectors for all chunks of this document are deleted from the `tenant_<id>` collection.
2. Chunk records are deleted from the PostgreSQL `chunks` table.
3. The document's `status` in the PostgreSQL `doc` table is set to `"deleted"`.

#### Response `200 OK`

```json
{
  "message": "Document deleted successfully"
}
```

#### Response `401 Unauthorized`

```json
{
  "detail": "Invalid or missing API Key"
}
```

---

### DELETE /delete_tenant

Delete all data for a tenant — their Qdrant collection, all document records, and all chunk records.

**Authentication:** `X-API-KEY` header  
**Content-Type:** `application/json`

#### Request Body

```json
{
  "tenant_id": "42"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tenant_id` | string | Yes | The tenant to purge. |

> ⚠️ **Destructive operation.** This permanently removes the tenant's Qdrant collection and all associated PostgreSQL records. It cannot be undone.

#### Deletion Cascade

1. The entire `tenant_<id>` Qdrant collection is dropped.
2. All `Chunk` rows with `tenant_id = <id>` are deleted.
3. All `Document` rows with `tenant_id = <id>` are deleted.

#### Response `200 OK`

```json
{
  "message": "Tenant deleted successfully"
}
```

#### Response `401 Unauthorized`

```json
{
  "detail": "Invalid or missing API Key"
}
```

---

## 5. Query

### POST /query

Submit a natural language query against a tenant's ingested documents. The system retrieves semantically relevant chunks, constructs a grounded prompt, and returns an LLM-generated answer.

**Authentication:** None (rate-limited by IP)  
**Content-Type:** `application/json`

#### Request Body

```json
{
  "text": "What are the key findings in the Q3 financial report?",
  "tenant_id": 42
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | The natural language query. |
| `tenant_id` | integer | Yes | The tenant whose documents to search. |

#### Processing Pipeline

1. Check Redis cache — if a matching response exists (SHA-256 keyed on query text), return it immediately.
2. Sanitize input — detect prompt injection, mask PII (SSNs, credit cards), score risk.
3. Embed the query using `all-MiniLM-L6-v2`.
4. Search the tenant's Qdrant collection for the top-5 most similar chunks.
5. Classify query intent — route to the fast model (Llama 3.1 8B) for simple queries, primary model (Llama 3.3 70B) for complex ones.
6. Build a grounded system prompt with the retrieved context.
7. Invoke the selected LLM. Validate and sanitize output.
8. Cache the result and log to MongoDB.

#### Response `200 OK`

```json
{
  "query_id": "uuid-string",
  "answer": "The Q3 report highlights a 12% revenue increase driven by...",
  "token_usage": {
    "input_tokens": 1024,
    "output_tokens": 256,
    "model": "llama-3.3-70b-versatile"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `query_id` | string (UUID) | Unique identifier for this query invocation. Used for log tracing. |
| `answer` | string | The LLM-generated answer, grounded in retrieved context. |
| `token_usage` | object \| null | Token consumption details. `null` if served from cache. |

#### Response `429 Too Many Requests`

```json
{
  "detail": "Rate limit exceeded (10 requests per 60 seconds)"
}
```

#### Response `500 Internal Server Error`

Returned if all models in the fallback chain are unhealthy or if output validation fails.

```json
{
  "detail": "All models unhealthy — serving degraded response"
}
```

---

## 6. Error Reference

| HTTP Status | Meaning | Common Causes |
|-------------|---------|---------------|
| `400 Bad Request` | Invalid request body or business rule violation | Malformed email, non-PDF file upload, missing required field |
| `401 Unauthorized` | Authentication failure | Missing/invalid bearer token, missing/invalid API key, invalid credentials |
| `422 Unprocessable Entity` | Pydantic validation failure | Field type mismatch, constraint violation (e.g., password too short) |
| `429 Too Many Requests` | Rate limit exceeded | More than 10 `POST /query` requests per 60 seconds from the same IP |
| `500 Internal Server Error` | Unhandled server-side error | PDF parse failure, all LLMs down, database connection error |
| `503 Service Unavailable` | Dependency health check failure | PostgreSQL unreachable at startup health check |
