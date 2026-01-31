# Vector Store for RAG
# Uses ChromaDB for local vector storage

import os
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

from .rag_config import CHROMA_PERSIST_DIR, COLLECTION_NAME, TOP_K_RESULTS
from .embeddings import embed_text


# Global client and collection
_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[chromadb.Collection] = None


def init_vector_store() -> chromadb.Collection:
    """
    Initialize ChromaDB and return the collection.
    Creates the database if it doesn't exist.
    """
    global _client, _collection
    
    if _collection is not None:
        return _collection
    
    # Ensure directory exists
    os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
    
    # Initialize ChromaDB with persistence
    _client = chromadb.PersistentClient(
        path=CHROMA_PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False)
    )
    
    # Get or create collection with cosine distance
    # Cosine distance gives us 0-1 range: 0 = identical, 1 = opposite
    _collection = _client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={
            "description": "Medical guidelines for RAG",
            "hnsw:space": "cosine"  # Use cosine distance for meaningful similarity scores
        }
    )
    
    return _collection


def add_documents(
    documents: List[str],
    metadatas: List[Dict[str, Any]],
    ids: List[str]
) -> None:
    """
    Add documents to the vector store.
    
    Args:
        documents: List of text chunks
        metadatas: List of metadata dicts (title, page, etc.)
        ids: List of unique IDs for each chunk
    """
    collection = init_vector_store()
    
    # ChromaDB can generate embeddings automatically, but we'll use our own
    # for consistency with Bedrock Titan
    from .embeddings import embed_texts
    embeddings = embed_texts(documents)
    
    collection.add(
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids
    )


def search(query: str, top_k: int = TOP_K_RESULTS) -> Dict[str, Any]:
    """
    Search for documents similar to the query.
    
    Args:
        query: The search query
        top_k: Number of results to return
        
    Returns:
        Dict with 'documents', 'metadatas', 'distances'
    """
    collection = init_vector_store()
    
    # Get embedding for query
    query_embedding = embed_text(query)
    
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )
    
    return results


def get_document_count() -> int:
    """Get the number of documents in the vector store."""
    collection = init_vector_store()
    return collection.count()


def clear_collection() -> None:
    """Clear all documents from the collection."""
    global _collection
    if _client is not None:
        _client.delete_collection(COLLECTION_NAME)
        _collection = None
        init_vector_store()  # Recreate empty collection
