# RAG Configuration

import os

# Embedding settings
EMBEDDING_MODEL = "amazon.titan-embed-text-v1"
EMBEDDING_DIMENSION = 1536

# Chunking settings
CHUNK_SIZE = 500  # characters
CHUNK_OVERLAP = 50  # characters

# Embedded vector-store settings
VECTOR_STORE_DIR = os.getenv(
    "VECTOR_STORE_DIR",
    os.path.join(os.path.dirname(__file__), "..", "vector_data"),
)
VECTOR_STORE_PATH = os.path.join(VECTOR_STORE_DIR, "vectors.sqlite3")

# Retrieval settings
TOP_K_RESULTS = 3
MIN_RELEVANCE_SCORE = 0.5
