import os


# Embedding model used for similarity search (Ollama by default).
EMBEDDING_MODEL = os.getenv("SCIFI_EMBEDDING_MODEL", "embeddinggemma")

# Versioned collection name to allow future embedding migrations.
CHROMA_COLLECTION = os.getenv(
    "SCIFI_CHROMA_COLLECTION",
    "works_v1_embeddinggemma",
)

# Optional: where to persist ChromaDB data on disk.
CHROMA_PERSIST_DIR = os.getenv("SCIFI_CHROMA_PERSIST_DIR", "data/chroma")
