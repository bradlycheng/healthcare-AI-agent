#!/usr/bin/env python3
"""
Script to index documents into the RAG vector store.
Run this once to populate the knowledge base with medical guidelines.

Usage:
    python scripts/index_documents.py
    python scripts/index_documents.py --clear  # Clear and reindex
"""

import argparse
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.document_loader import index_directory
from app.vector_store import get_document_count, clear_collection


def main():
    parser = argparse.ArgumentParser(description="Index documents for RAG")
    parser.add_argument("--clear", action="store_true", help="Clear existing documents before indexing")
    parser.add_argument("--dir", default="docs", help="Directory containing documents to index")
    args = parser.parse_args()
    
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), args.dir)
    
    if not os.path.exists(docs_dir):
        print(f"Error: Documents directory not found: {docs_dir}")
        sys.exit(1)
    
    print(f"\n📚 RAG Document Indexer")
    print(f"=" * 50)
    
    # Show current state
    current_count = get_document_count()
    print(f"Current chunks in vector store: {current_count}")
    
    if args.clear:
        print("\n🗑️  Clearing existing documents...")
        clear_collection()
        print("  Done!")
    
    print(f"\n📂 Indexing documents from: {docs_dir}")
    
    results = index_directory(docs_dir)
    
    total_chunks = sum(results.values())
    print(f"\n✅ Indexing complete!")
    print(f"   Documents processed: {len(results)}")
    print(f"   Total chunks created: {total_chunks}")
    print(f"   Total chunks in store: {get_document_count()}")


if __name__ == "__main__":
    main()
