from supabase import create_client, Client
from qdrant_client import QdrantClient
from rag_project.doc_ingestion_microservice.config.settings import settings

# Supabase
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.FINAL_SUPABASE_KEY
)

# Qdrant
qdrant = QdrantClient(
    url=settings.QDRANT_URL,
    api_key=settings.QDRANT_API_KEY
)

print("Database clients initialized")