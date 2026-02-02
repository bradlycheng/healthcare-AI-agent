from app.document_loader import chunk_text
import sys
import threading
import time

def test_chunking():
    print("Starting chunk_text test...")
    text = "Sentence one. Sentence two. Sentence three."
    try:
        # Use a timeout to detect infinite loop
        start = time.time()
        chunks = chunk_text(text, chunk_size=20, overlap=5)
        print(f"Chunks created: {len(chunks)}")
        for i, c in enumerate(chunks):
            print(f"  Chunk {i}: {c!r}")
        print("Success!")
    except Exception:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_chunking()
