"""Small embedded vector store for local RAG retrieval."""

from __future__ import annotations

import json
import math
import os
import sqlite3
from typing import Any, Dict, List

from .embeddings import embed_text
from .rag_config import TOP_K_RESULTS, VECTOR_STORE_PATH


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(VECTOR_STORE_PATH), exist_ok=True)
    connection = sqlite3.connect(VECTOR_STORE_PATH, timeout=30.0)
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_documents (
            id TEXT PRIMARY KEY,
            document TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            embedding_json TEXT NOT NULL
        )
        """
    )
    return connection


def init_vector_store() -> None:
    """Create the local vector-store schema when needed."""
    with _connect():
        pass


def add_documents(
    documents: List[str],
    metadatas: List[Dict[str, Any]],
    ids: List[str],
) -> None:
    """Embed and upsert documents into the local store."""
    if not (len(documents) == len(metadatas) == len(ids)):
        raise ValueError("documents, metadatas, and ids must have equal lengths")

    from .embeddings import embed_texts

    embeddings = embed_texts(documents)
    rows = [
        (
            document_id,
            document,
            json.dumps(metadata, ensure_ascii=True),
            json.dumps([float(value) for value in embedding]),
        )
        for document_id, document, metadata, embedding
        in zip(ids, documents, metadatas, embeddings)
    ]

    with _connect() as connection:
        connection.executemany(
            """
            INSERT INTO rag_documents (id, document, metadata_json, embedding_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                document = excluded.document,
                metadata_json = excluded.metadata_json,
                embedding_json = excluded.embedding_json
            """,
            rows,
        )


def _cosine_distance(left: List[float], right: List[float]) -> float:
    if len(left) != len(right) or not left:
        return 1.0

    dot_product = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 1.0

    similarity = max(-1.0, min(1.0, dot_product / (left_norm * right_norm)))
    return 1.0 - similarity


def search(query: str, top_k: int = TOP_K_RESULTS) -> Dict[str, Any]:
    """Return closest documents using the retrieval contract expected by the app."""
    query_embedding = [float(value) for value in embed_text(query)]

    with _connect() as connection:
        rows = connection.execute(
            "SELECT document, metadata_json, embedding_json FROM rag_documents"
        ).fetchall()

    ranked = []
    for document, metadata_json, embedding_json in rows:
        embedding = [float(value) for value in json.loads(embedding_json)]
        ranked.append(
            (
                _cosine_distance(query_embedding, embedding),
                document,
                json.loads(metadata_json),
            )
        )

    ranked.sort(key=lambda item: item[0])
    selected = ranked[:max(0, top_k)]
    return {
        "documents": [[item[1] for item in selected]],
        "metadatas": [[item[2] for item in selected]],
        "distances": [[item[0] for item in selected]],
    }


def get_document_count() -> int:
    """Get the number of indexed document chunks."""
    with _connect() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM rag_documents").fetchone()[0])


def clear_collection() -> None:
    """Remove all indexed document chunks."""
    with _connect() as connection:
        connection.execute("DELETE FROM rag_documents")
