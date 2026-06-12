import os
import sys

# Ensure app is in path when this script is run directly.
sys.path.append(os.getcwd())

from app.document_loader import index_directory
from app.rag_config import VECTOR_STORE_DIR


def main():
    docs_dir = os.path.join(os.getcwd(), "docs")
    print(f"Ingesting documents from {docs_dir}...")
    print(f"Persisting to {VECTOR_STORE_DIR}")

    results = index_directory(docs_dir)

    print("\n--- Ingestion Results ---")
    total_chunks = 0
    for filename, count in results.items():
        print(f"- {filename}: {count} chunks")
        total_chunks += count

    print(f"\nTotal chunks indexed: {total_chunks}")
    if results and total_chunks == 0:
        print("RAG indexing produced no chunks.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
