# RAG Configuration

import os

# Embedding settings
EMBEDDING_MODEL = "amazon.titan-embed-text-v1"
EMBEDDING_DIMENSION = 1536

# Chunking settings
CHUNK_SIZE = 500  # characters
CHUNK_OVERLAP = 50  # characters

# Vector DB settings
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
COLLECTION_NAME = "medical_guidelines"

# Retrieval settings
TOP_K_RESULTS = 3
MIN_RELEVANCE_SCORE = 0.5
