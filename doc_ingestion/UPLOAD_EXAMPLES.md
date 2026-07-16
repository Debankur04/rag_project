# Document Upload API Examples

This file provides examples for testing the `/add_doc` and `/add_docs` endpoints.

## Prerequisites

- Authentication token (get from `/auth/login` or `/auth/register`)
- One or more PDF files to upload
- The API should be running at `http://localhost:8000`

## Single File Upload — `/add_doc`

### Using curl

```bash
curl -X POST http://localhost:8000/add_doc \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@/path/to/document.pdf"
```

### Using JavaScript/Fetch

```javascript
const file = document.querySelector('input[type="file"]').files[0];
const token = localStorage.getItem('access_token');

const formData = new FormData();
formData.append('file', file);

const response = await fetch('http://localhost:8000/add_doc', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`
  },
  body: formData
});

const result = await response.json();
console.log(result);
// {
//   "file_name": "document.pdf",
//   "ingestion_id": "uuid-string",
//   "status": "success",
//   "error": null,
//   "document": { ... }
// }
```

### Using Python/requests

```python
import requests

token = "YOUR_JWT_TOKEN"
files = {'file': open('document.pdf', 'rb')}
headers = {'Authorization': f'Bearer {token}'}

response = requests.post(
    'http://localhost:8000/add_doc',
    files=files,
    headers=headers
)

print(response.json())
```

---

## Multiple Files Upload — `/add_docs`

### Using curl

```bash
curl -X POST http://localhost:8000/add_docs \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "files=@/path/to/document1.pdf" \
  -F "files=@/path/to/document2.pdf" \
  -F "files=@/path/to/document3.pdf"
```

### Using JavaScript/Fetch

```javascript
const files = document.querySelector('input[type="file"]').files; // Multiple files
const token = localStorage.getItem('access_token');

const formData = new FormData();

// Add all files to FormData with the same field name 'files'
for (const file of files) {
  formData.append('files', file);
}

const response = await fetch('http://localhost:8000/add_docs', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`
  },
  body: formData
});

const result = await response.json();
console.log(`Successfully uploaded: ${result.success}/${result.total}`);
console.log(result.results);
// {
//   "message": "Bulk document ingestion completed",
//   "total": 3,
//   "success": 2,
//   "failed": 1,
//   "results": [
//     {
//       "file_name": "document1.pdf",
//       "status": "success",
//       "error": null,
//       "document": { ... }
//     },
//     { ... more results ... }
//   ]
// }
```

### Using Python/requests

```python
import requests

token = "YOUR_JWT_TOKEN"
files = [
    ('files', open('document1.pdf', 'rb')),
    ('files', open('document2.pdf', 'rb')),
    ('files', open('document3.pdf', 'rb')),
]
headers = {'Authorization': f'Bearer {token}'}

response = requests.post(
    'http://localhost:8000/add_docs',
    files=files,
    headers=headers
)

result = response.json()
print(f"Successfully uploaded: {result['success']}/{result['total']}")
print(result['results'])
```

### Using Postman

1. Create a new POST request to `http://localhost:8000/add_docs`
2. In the **Authorization** tab:
   - Type: Bearer Token
   - Token: `YOUR_JWT_TOKEN`
3. In the **Body** tab:
   - Select `form-data`
   - Add multiple rows with:
     - Key: `files`
     - Type: File
     - Value: Select your PDF files
4. Click **Send**

---

## Response Format

### Success Response (200 OK)

```json
{
  "message": "Bulk document ingestion completed",
  "total": 2,
  "success": 2,
  "failed": 0,
  "results": [
    {
      "file_name": "document1.pdf",
      "ingestion_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "success",
      "error": null,
      "document": {
        "id": 123,
        "user_id": "user-uuid",
        "file_name": "document1.pdf",
        "status": "ingested",
        "chunk_count": 45,
        "duplicate": false
      }
    },
    {
      "file_name": "document2.pdf",
      "ingestion_id": "550e8400-e29b-41d4-a716-446655440001",
      "status": "success",
      "error": null,
      "document": {
        "id": 124,
        "user_id": "user-uuid",
        "file_name": "document2.pdf",
        "status": "ingested",
        "chunk_count": 32,
        "duplicate": false
      }
    }
  ]
}
```

### Mixed Success/Failure Response

```json
{
  "message": "Bulk document ingestion completed",
  "total": 3,
  "success": 1,
  "failed": 2,
  "results": [
    {
      "file_name": "valid.pdf",
      "ingestion_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "success",
      "error": null,
      "document": { ... }
    },
    {
      "file_name": "image.png",
      "ingestion_id": null,
      "status": "failed",
      "error": "Only PDF uploads are supported",
      "document": null
    },
    {
      "file_name": "corrupted.pdf",
      "ingestion_id": "550e8400-e29b-41d4-a716-446655440002",
      "status": "failed",
      "error": "No readable content found in PDF",
      "document": null
    }
  ]
}
```

### Error Response (400 Bad Request)

```json
{
  "detail": "Maximum 10 files per request. Please upload in batches."
}
```

---

## Common Issues and Solutions

### Issue: "Only PDF uploads are supported"
- **Cause**: You're trying to upload a non-PDF file
- **Solution**: Make sure all files have `.pdf` extension and are valid PDF files

### Issue: "No files provided"
- **Cause**: The request body doesn't contain any files
- **Solution**: Make sure you're using the correct form field name (`files` for `/add_docs`, `file` for `/add_doc`)

### Issue: "Maximum 10 files per request"
- **Cause**: You're trying to upload more than 10 files at once
- **Solution**: Split your uploads into batches of 10 or fewer files

### Issue: "401 Unauthorized"
- **Cause**: Missing or invalid authentication token
- **Solution**: Make sure your JWT token is valid and included in the `Authorization: Bearer <token>` header

### Issue: Individual files fail but others succeed
- **Cause**: Some files may have issues (corrupted, not readable, etc.)
- **Solution**: Check the error messages in the results array for each failed file

---

## Performance Notes

- Maximum files per request: **10**
- Each file is processed sequentially within a single request
- Large files may take longer to process (OCR + embedding generation)
- Failed files don't prevent other files from processing
- Duplicate files (same content hash) are detected and skipped

---

## Integration Example

Here's a complete example of a document upload component:

```javascript
async function uploadDocuments(files, token) {
  const formData = new FormData();
  
  for (const file of files) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      console.warn(`Skipping ${file.name}: not a PDF`);
      continue;
    }
    formData.append('files', file);
  }
  
  if (formData.getAll('files').length === 0) {
    throw new Error('No valid PDF files to upload');
  }
  
  const response = await fetch('http://localhost:8000/add_docs', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    },
    body: formData
  });
  
  const result = await response.json();
  
  if (!response.ok) {
    throw new Error(result.detail || 'Upload failed');
  }
  
  return {
    successful: result.results.filter(r => r.status === 'success'),
    failed: result.results.filter(r => r.status === 'failed'),
    stats: {
      total: result.total,
      success: result.success,
      failed: result.failed
    }
  };
}

// Usage
try {
  const result = await uploadDocuments(
    document.querySelector('input[type="file"]').files,
    localStorage.getItem('access_token')
  );
  
  console.log(`Uploaded ${result.stats.success} documents`);
  
  result.failed.forEach(f => {
    console.error(`Failed: ${f.file_name} - ${f.error}`);
  });
} catch (error) {
  console.error('Upload error:', error);
}
```
