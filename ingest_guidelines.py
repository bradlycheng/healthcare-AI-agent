import sys
import os

# Ensure app is in path
sys.path.append(os.getcwd())

from app.document_loader import index_directory
from app.rag_config import CHROMA_PERSIST_DIR

def main():
    docs_dir = os.path.join(os.getcwd(), "docs")
    print(f"Ingesting documents from {docs_dir}...")
    print(f"Persisting to {CHROMA_PERSIST_DIR}")
    
    results = index_directory(docs_dir)
    
    print("\n--- Ingestion Results ---")
    total_chunks = 0
    for file, count in results.items():
        print(f"📄 {file}: {count} chunks")
        total_chunks += count
        
    print(f"\n✅ Total Chunks Indexed: {total_chunks}")

if __name__ == "__main__":
    main()
