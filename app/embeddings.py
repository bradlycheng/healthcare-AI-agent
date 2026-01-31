# Embedding utilities for RAG
# Uses AWS Bedrock Titan Embeddings

import json
import os
from typing import List

import boto3
from botocore.config import Config

from .rag_config import EMBEDDING_MODEL, EMBEDDING_DIMENSION


def get_bedrock_client():
    """Get Bedrock runtime client."""
    region = os.getenv("AWS_REGION", "us-east-1")
    config = Config(
        retries={"max_attempts": 3, "mode": "adaptive"},
        read_timeout=30,
    )
    return boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=config,
    )


def embed_text(text: str) -> List[float]:
    """
    Generate embedding for a single text using Bedrock Titan.
    
    Args:
        text: The text to embed
        
    Returns:
        List of floats representing the embedding vector
    """
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIMENSION
    
    client = get_bedrock_client()
    
    # Titan expects this format
    body = json.dumps({
        "inputText": text[:8000]  # Titan has 8k token limit
    })
    
    response = client.invoke_model(
        modelId=EMBEDDING_MODEL,
        body=body,
        contentType="application/json",
        accept="application/json"
    )
    
    response_body = json.loads(response["body"].read())
    embedding = response_body.get("embedding", [])
    
    return embedding


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for multiple texts.
    
    Args:
        texts: List of texts to embed
        
    Returns:
        List of embedding vectors
    """
    embeddings = []
    for text in texts:
        embedding = embed_text(text)
        embeddings.append(embedding)
    return embeddings
