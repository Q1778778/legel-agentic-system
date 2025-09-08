"""Embedding service for text vectorization."""

from typing import List, Optional
import openai
from openai import AsyncOpenAI
import numpy as np
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
import tiktoken
import hashlib
import json

from ..core.config import settings

logger = structlog.get_logger()


class EmbeddingService:
    """Service for generating text embeddings."""
    
    def __init__(self):
        """Initialize embedding service."""
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.embedding_model
        self.encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        self.max_tokens = 8191  # Max for text-embedding-3-small
        self._cache = {}  # Simple in-memory cache
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def embed_text(
        self,
        text: str,
        use_cache: bool = True,
    ) -> List[float]:
        """Generate embedding for text.
        
        Args:
            text: Text to embed
            use_cache: Whether to use cache
            
        Returns:
            Embedding vector
        """
        try:
            # Check cache
            if use_cache:
                cache_key = self._get_cache_key(text)
                if cache_key in self._cache:
                    logger.debug("Using cached embedding")
                    return self._cache[cache_key]
            
            # Truncate if necessary
            truncated_text = self._truncate_text(text)
            
            # Generate embedding
            response = await self.client.embeddings.create(
                model=self.model,
                input=truncated_text,
            )
            
            embedding = response.data[0].embedding
            
            # Cache result
            if use_cache:
                self._cache[cache_key] = embedding
            
            logger.debug(f"Generated embedding for text of length {len(text)}")
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            batch_size: Batch size for API calls
            
        Returns:
            List of embedding vectors
        """
        try:
            embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                
                # Truncate texts
                truncated_batch = [self._truncate_text(t) for t in batch]
                
                # Generate embeddings
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=truncated_batch,
                )
                
                batch_embeddings = [item.embedding for item in response.data]
                embeddings.extend(batch_embeddings)
                
                logger.debug(f"Generated {len(batch_embeddings)} embeddings in batch")
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            raise
    
    def _truncate_text(self, text: str) -> str:
        """Truncate text to fit within token limits.
        
        Args:
            text: Text to truncate
            
        Returns:
            Truncated text
        """
        try:
            tokens = self.encoding.encode(text)
            if len(tokens) > self.max_tokens:
                tokens = tokens[:self.max_tokens]
                text = self.encoding.decode(tokens)
                logger.warning(f"Truncated text from {len(tokens)} to {self.max_tokens} tokens")
            return text
        except Exception:
            # Fallback to character truncation
            max_chars = self.max_tokens * 4  # Rough estimate
            if len(text) > max_chars:
                text = text[:max_chars]
            return text
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text.
        
        Args:
            text: Text to hash
            
        Returns:
            Cache key
        """
        return hashlib.md5(f"{self.model}:{text}".encode()).hexdigest()
    
    def calculate_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float],
    ) -> float:
        """Calculate cosine similarity between embeddings.
        
        Args:
            embedding1: First embedding
            embedding2: Second embedding
            
        Returns:
            Similarity score (0-1)
        """
        try:
            # Convert to numpy arrays
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            # Normalize
            vec1 = vec1 / np.linalg.norm(vec1)
            vec2 = vec2 / np.linalg.norm(vec2)
            
            # Calculate cosine similarity
            similarity = np.dot(vec1, vec2)
            
            # Ensure in range [0, 1]
            return float(max(0, min(1, (similarity + 1) / 2)))
            
        except Exception as e:
            logger.error(f"Error calculating similarity: {e}")
            return 0.0
    
    def chunk_text(
        self,
        text: str,
        chunk_size: int = 400,
        overlap: int = 50,
    ) -> List[str]:
        """Chunk text for embedding.
        
        Args:
            text: Text to chunk
            chunk_size: Target chunk size in tokens
            overlap: Overlap between chunks in tokens
            
        Returns:
            List of text chunks
        """
        try:
            tokens = self.encoding.encode(text)
            chunks = []
            
            start = 0
            while start < len(tokens):
                end = min(start + chunk_size, len(tokens))
                chunk_tokens = tokens[start:end]
                chunk_text = self.encoding.decode(chunk_tokens)
                chunks.append(chunk_text)
                
                # Move start with overlap
                start = end - overlap if end < len(tokens) else end
            
            logger.debug(f"Split text into {len(chunks)} chunks")
            return chunks
            
        except Exception as e:
            logger.error(f"Error chunking text: {e}")
            # Fallback to character-based chunking
            char_size = chunk_size * 4  # Rough estimate
            char_overlap = overlap * 4
            chunks = []
            
            start = 0
            while start < len(text):
                end = min(start + char_size, len(text))
                chunks.append(text[start:end])
                start = end - char_overlap if end < len(text) else end
            
            return chunks