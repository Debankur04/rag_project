# 📘 API Documentation – Multi-Tenant RAG Backend

This document describes the REST APIs exposed by the **RAG (Retrieval-Augmented Generation) backend**, designed to support **multi-tenant document ingestion, querying, deletion, and health monitoring**.

---

## 🌐 Base URL

```
http://<host>:<port>
```

Example (local):
```
http://localhost:8000
```

---

## 🩺 Health & Status APIs

### 1️⃣ Root Health Check

**Endpoint**
```
GET /
```

**Description**  
Basic liveness check to verify the API server is running.

**Response**
```json
{
  "message": "OK"
}
```

---

### 2️⃣ System Health Check

**Endpoint**
```
GET /health
```

**Description**  
Checks the readiness of all critical system components:
- API server
- Supabase database
- Qdrant vector database

This endpoint is suitable for:
- Load balancers
- Docker / Kubernetes readiness checks
- Monitoring systems (Prometheus / Grafana)

**Response**
```json
{
  "status": "ok",
  "timestamp": "2026-01-16T18:12:03.921Z",
  "services": {
    "api": "ok",
    "database": "ok",
    "vector_db": "ok"
  }
}
```

---

## 💬 Query (RAG / Chat)

### 3️⃣ Query Documents

**Endpoint**
```
POST /query
```

**Request Body**
```json
{
  "tenant_id": "string",
  "text": "string",
  "history": "string"
}
```

**Response**
```json
{
  "rag_response": "string"
}
```

---

## 📄 Document Management

### 4️⃣ Add Document

**Endpoint**
```
POST /add_doc?tenant_id=<tenant_id>
```

**Body**
- multipart/form-data
- key: `doc` (PDF file)

**Response**
```json
{
  "message": "Document processed successfully"
}
```

---

## 🗑️ Deletion APIs

### 5️⃣ Delete Document

**Endpoint**
```
DELETE /delete_doc
```

**Request Body**
```json
{
  "tenant_id": "string",
  "doc_id": "uuid",
  "name": "string"
}
```

---

### 6️⃣ Delete Tenant

**Endpoint**
```
DELETE /delete_tenant
```

**Request Body**
```json
{
  "tenant_id": "string"
}
```

---

## 🔐 Multi-Tenancy Guarantees

- Strict tenant isolation
- Dedicated Qdrant collections
- SQL scoping by tenant_id

---

## 🧪 Recommended Testing Order

1. GET /
2. GET /health
3. POST /add_doc
4. POST /query
5. DELETE /delete_doc
6. DELETE /delete_tenant
