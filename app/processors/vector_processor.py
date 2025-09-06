import numpy as np
import hashlib
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models import DocumentChunk
from app.processors.chunk_processor import chunk_processor
from app.config import settings
import traceback
import logging
import uuid

logger = logging.getLogger(__name__)

class SimpleCache:
    def __init__(self, max_size: int = 1000):
        self.cache = {}
        self.max_size = max_size
    
    def get(self, key: str):
        return self.cache.get(key)
    
    def set(self, key: str, value):
        if len(self.cache) >= self.max_size:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = value
    
    def clear(self):
        self.cache.clear()

class VectorProcessor:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.rag.embedding_model_name
        self.model = SentenceTransformer(self.model_name)
        self.embedding_cache = SimpleCache(max_size=settings.vector.max_cache_size)
        self.batch_size = settings.rag.embedding_batch_size
    
    def _hash_content(self, content: str) -> str:
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        try:
            if not texts:
                return []
            
            embeddings = []
            texts_to_embed = []
            text_indices = []
            
            # Batch cache lookup for better performance
            for i, text in enumerate(texts):
                cache_key = self._hash_content(text)
                cached = self.embedding_cache.get(cache_key)
                if cached is not None:
                    embeddings.append((i, cached))
                else:
                    texts_to_embed.append(text)
                    text_indices.append(i)
            
            if texts_to_embed:
                logger.info(f"Generating embeddings for {len(texts_to_embed)} texts (batch size: {self.batch_size})")
                
                # Optimized embedding generation with better batching
                new_embeddings = self.model.encode(
                    texts_to_embed, 
                    normalize_embeddings=True,
                    batch_size=self.batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,  # More efficient
                    device=None  # Let sentence-transformers choose best device
                ).tolist()
                
                # Batch cache updates
                for text, embedding in zip(texts_to_embed, new_embeddings):
                    cache_key = self._hash_content(text)
                    self.embedding_cache.set(cache_key, embedding)
                
                for i, embedding in zip(text_indices, new_embeddings):
                    embeddings.append((i, embedding))
            
            embeddings.sort(key=lambda x: x[0])
            return [emb for _, emb in embeddings]
            
        except Exception as e:
            logger.error(f"Error creating embeddings: {e}")
            traceback.print_exc()
            raise
    
    def chunk_and_embed_document(self, db: Session, document_id: str, text_content: str) -> List[DocumentChunk]:
        try:
            logger.info(f"Processing document {document_id} with {len(text_content)} characters")
            
            existing_chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id
            ).first()
            
            if existing_chunks:
                logger.info(f"Document {document_id} already has chunks")
                return db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == document_id
                ).all()
            
            word_count = len(text_content.split())
            text_splitter = chunk_processor.setup_text_splitter(word_count)
            chunks = text_splitter.split_text(text_content)
            
            if not chunks:
                logger.warning(f"No chunks created for document {document_id}")
                return []
            
            logger.info(f"Created {len(chunks)} chunks for document {document_id}")
            
            embeddings = self.create_embeddings(chunks)
            
            if len(embeddings) != len(chunks):
                raise ValueError(f"Embedding count {len(embeddings)} doesn't match chunk count {len(chunks)}")
            
            chunk_objects = []
            for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_obj = DocumentChunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    chunk_index=i,
                    content=chunk_text,
                    word_count=len(chunk_text.split()),
                    embedding=embedding,
                    extra_metadata={
                        "chunk_length": len(chunk_text),
                        "word_count": len(chunk_text.split()),
                        "content_hash": self._hash_content(chunk_text)
                    }
                )
                chunk_objects.append(chunk_obj)
            
            db.bulk_insert_mappings(DocumentChunk, [
                {
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "word_count": chunk.word_count,
                    "embedding": chunk.embedding,
                    "extra_metadata": chunk.extra_metadata,
                    "created_at": chunk.created_at
                }
                for chunk in chunk_objects
            ])
            
            db.commit()
            logger.info(f"Successfully created {len(chunk_objects)} chunks with embeddings")
            return chunk_objects
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error chunking and embedding document {document_id}: {e}")
            traceback.print_exc()
            raise
    
    def similarity_search(self, db: Session, query: str, document_ids: List[str] = None, 
                         top_k: int = 10) -> List[Dict[str, Any]]:
        try:
            if not query.strip():
                logger.warning("Empty query provided")
                return []
            
            query_embedding = self.create_embeddings([query])[0]
            
            similarity_query = """
                SELECT 
                    id,
                    document_id,
                    chunk_index,
                    content,
                    word_count,
                    extra_metadata,
                    1 - (embedding <=> :query_embedding) as similarity_score
                FROM document_chunks 
            """
            
            params = {"query_embedding": str(query_embedding)}
            
            if document_ids:
                placeholders = ','.join([f':doc_id_{i}' for i in range(len(document_ids))])
                similarity_query += f" WHERE document_id IN ({placeholders})"
                for i, doc_id in enumerate(document_ids):
                    params[f'doc_id_{i}'] = doc_id
            
            similarity_query += f" ORDER BY similarity_score DESC LIMIT :top_k"
            params["top_k"] = top_k
            
            result = db.execute(text(similarity_query), params)
            results = result.fetchall()
            
            search_results = []
            for row in results:
                if row.similarity_score >= settings.rag.similarity_threshold:
                    search_results.append({
                        "id": str(row.id),
                        "document_id": str(row.document_id),
                        "chunk_index": row.chunk_index,
                        "content": row.content,
                        "word_count": row.word_count,
                        "extra_metadata": row.extra_metadata,
                        "similarity_score": float(row.similarity_score)
                    })
            
            logger.info(f"Similarity search returned {len(search_results)} results")
            return search_results
            
        except Exception as e:
            logger.error(f"Error in similarity search: {e}")
            traceback.print_exc()
            return []
    
    def get_relevant_context(self, db: Session, topic: str, document_ids: List[str] = None, 
                           max_context_length: int = None) -> str:
        try:
            if max_context_length is None:
                max_context_length = settings.rag.max_context_length
            
            search_results = self.similarity_search(
                db, topic, document_ids, top_k=settings.rag.retrieval_top_k
            )
            
            if not search_results:
                logger.warning(f"No relevant context found for topic: {topic}")
                return ""
            
            context_parts = []
            current_length = 0
            
            for result in search_results:
                content = result['content'].strip()
                content_length = len(content)
                
                if current_length + content_length <= max_context_length:
                    context_parts.append(content)
                    current_length += content_length
                else:
                    remaining_space = max_context_length - current_length
                    if remaining_space > settings.vector.min_context_chars:
                        truncated = content[:remaining_space - 3] + "..."
                        context_parts.append(truncated)
                    break
            
            context = settings.vector.context_separator.join(context_parts)
            logger.info(f"Retrieved context of {len(context)} characters from {len(context_parts)} chunks")
            return context
            
        except Exception as e:
            logger.error(f"Error getting relevant context: {e}")
            traceback.print_exc()
            return ""
    
    def get_cache_stats(self) -> Dict[str, Any]:
        return {
            "cache_size": len(self.embedding_cache.cache),
            "max_cache_size": self.embedding_cache.max_size,
            "model_name": self.model_name
        }
    
    def cleanup_cache(self) -> int:
        cache_size = len(self.embedding_cache.cache)
        self.embedding_cache.clear()
        logger.info(f"Cleared {cache_size} cached embeddings")
        return cache_size

vector_processor = VectorProcessor()