# Document Loader for RAG
# Loads and chunks documents for vector storage

import os
import re
from typing import Dict, List, Tuple

from .rag_config import CHUNK_SIZE, CHUNK_OVERLAP


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Split text into overlapping chunks.
    
    Args:
        text: The text to chunk
        chunk_size: Maximum size of each chunk
        overlap: Number of characters to overlap between chunks
        
    Returns:
        List of text chunks
    """
    if not text:
        return []
    
    # Clean the text
    text = re.sub(r'\s+', ' ', text).strip()
    
    chunks = []
    
    start = 0
    while True:
        end = start + chunk_size
        
        # If we reached the end of the text, stop
        if start >= len(text):
            break
            
        chunk = text[start:end]
        chunks.append(chunk)

        if end >= len(text):
            break
            
        next_start = end - overlap
        if next_start < 0:
            next_start = 0
            
        # Ensure we always make progress
        if next_start <= start:
            next_start = start + 1
            
        start = next_start
    
    return chunks


def load_text_file(path: str) -> str:
    """Load text from a file."""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def load_pdf_file(path: str) -> str:
    """
    Load text from a PDF file.
    Requires pypdf to be installed.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("pypdf is required for PDF loading. Install with: pip install pypdf")
    
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text


def load_document(path: str) -> Tuple[str, str]:
    """
    Load a document from various formats.
    
    Args:
        path: Path to the document
        
    Returns:
        Tuple of (text content, document title)
    """
    filename = os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()
    
    if ext == '.pdf':
        text = load_pdf_file(path)
    elif ext in ['.txt', '.md']:
        text = load_text_file(path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
    
    # Try to extract a friendly title from the document content
    title = extract_title(text, filename)
    
    return text, title


def extract_title(text: str, fallback: str) -> str:
    """
    Extract a user-friendly title from document content.
    Looks for markdown headers like '# Medical Reference: Blood Glucose Guidelines'
    """
    # Look for markdown header patterns
    patterns = [
        r'^#\s*Medical Reference:\s*(.+)$',  # "# Medical Reference: Blood Glucose Guidelines"
        r'^#\s*(.+)$',                        # "# Title"
        r'^##\s*(.+)$',                       # "## Title"
    ]
    
    for line in text.split('\n')[:10]:  # Check first 10 lines
        line = line.strip()
        for pattern in patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                # Clean up the title
                title = re.sub(r'\s+', ' ', title)
                if len(title) > 5:  # Reasonable title length
                    return title
    
    # Fallback: clean up the filename
    title = fallback.replace('_', ' ').replace('.txt', '').replace('.pdf', '').replace('.md', '')
    return title.title()


def index_document(path: str) -> int:
    """
    Load, chunk, and index a single document.
    
    Args:
        path: Path to the document
        
    Returns:
        Number of chunks indexed
    """
    from .vector_store import add_documents
    
    text, title = load_document(path)
    chunks = chunk_text(text)
    
    if not chunks:
        return 0
    
    # Create IDs and metadata for each chunk
    ids = [f"{title}_{i}" for i in range(len(chunks))]
    metadatas = [
        {"title": title, "chunk_index": i, "source": path}
        for i in range(len(chunks))
    ]
    
    add_documents(chunks, metadatas, ids)
    
    return len(chunks)


def index_directory(dir_path: str, extensions: List[str] = ['.pdf', '.txt', '.md']) -> Dict[str, int]:
    """
    Index all documents in a directory.
    
    Args:
        dir_path: Path to the directory
        extensions: File extensions to include
        
    Returns:
        Dict mapping filename to number of chunks indexed
    """
    results = {}
    
    for filename in os.listdir(dir_path):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in extensions:
            continue
        
        filepath = os.path.join(dir_path, filename)
        try:
            count = index_document(filepath)
            results[filename] = count
            print(f"Indexed {filename}: {count} chunks")
        except Exception as e:
            print(f"Error indexing {filename}: {e}")
            results[filename] = 0
    
    return results
