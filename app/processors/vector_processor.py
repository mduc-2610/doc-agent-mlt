# app/processors/vector_processor.py
import numpy as np
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models import DocumentChunk, Document
from app.processors.chunk_processor import chunk_processor
from app.services.caching_service import caching_service
from app.config import settings
import traceback
import logging
import uuid
import re
from collections import Counter
import math

logger = logging.getLogger(__name__)

class HybridSearchProcessor:
    """Combines semantic and keyword search for better retrieval"""
    
    def __init__(self):
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those'
        }
    
    def preprocess_text(self, text: str) -> List[str]:
        """Preprocess text for keyword matching"""
        # Convert to lowercase and split
        words = re.findall(r'\b\w+\b', text.lower())
        # Remove stop words
        return [word for word in words if word not in self.stop_words and len(word) > 2]
    
    def calculate_bm25_score(self, query_terms: List[str], doc_terms: List[str], 
                           corpus_stats: Dict[str, Any]) -> float:
        """Calculate BM25 score for keyword matching"""
        k1, b = 1.5, 0.75  # BM25 parameters
        
        doc_len = len(doc_terms)
        avg_doc_len = corpus_stats.get('avg_doc_length', doc_len)
        
        score = 0.0
        doc_term_freq = Counter(doc_terms)
        
        for term in query_terms:
            if term in doc_term_freq:
                tf = doc_term_freq[term]
                # Simple IDF approximation (in production, calculate from corpus)
                idf = math.log(corpus_stats.get('total_docs', 1000) / 
                             max(corpus_stats.get(f'term_freq_{term}', 1), 1))
                
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * (doc_len / avg_doc_len))
                score += idf * (numerator / denominator)
        
        return score
    
    def hybrid_score(self, semantic_score: float, keyword_score: float, 
                    alpha: float = 0.7) -> float:
        """Combine semantic and keyword scores"""
        return alpha * semantic_score + (1 - alpha) * keyword_score

class VectorProcessor:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.rag.embedding_model_name
        self.model = SentenceTransformer(self.model_name)
        self.embedding_dimension = settings.rag.embedding_dimension
        self.hybrid_search = HybridSearchProcessor()
        self.batch_size = settings.rag.embedding_batch_size
    
    def _hash_content(self, content: str) -> str:
        """Create hash for content caching"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Create embeddings with caching and batch processing"""
        try:
            if not texts:
                return []
            
            # Check cache for existing embeddings
            cached_embeddings = {}
            uncached_texts = []
            
            for i, text in enumerate(texts):
                cached_embedding = caching_service.get_embedding(text)
                if cached_embedding is not None:
                    cached_embeddings[i] = cached_embedding
                else:
                    uncached_texts.append((i, text))
            
            # Generate embeddings for uncached texts in batches
            if uncached_texts:
                indices, texts_to_embed = zip(*uncached_texts)
                
                logger.info(f"Generating embeddings for {len(texts_to_embed)} uncached texts")
                
                # Process in batches for memory efficiency
                new_embeddings = []
                for i in range(0, len(texts_to_embed), self.batch_size):
                    batch = texts_to_embed[i:i + self.batch_size]
                    
                    batch_embeddings = self.model.encode(
                        batch, 
                        normalize_embeddings=True,
                        batch_size=len(batch),
                        show_progress_bar=False
                    )
                    new_embeddings.extend(batch_embeddings.tolist())
                
                # Cache new embeddings
                for idx, (original_idx, text) in enumerate(uncached_texts):
                    embedding = new_embeddings[idx]
                    caching_service.set_embedding(text, embedding)
                    cached_embeddings[original_idx] = embedding
            
            # Return embeddings in original order
            result = [cached_embeddings[i] for i in range(len(texts))]
            logger.info(f"Generated/retrieved {len(result)} embeddings")
            return result
            
        except Exception as e:
            logger.error(f"Error creating embeddings: {e}")
            traceback.print_exc()
            raise
    
    def chunk_and_embed_document(self, db: Session, document_id: str, text_content: str) -> List[DocumentChunk]:
        """ chunking and embedding with better error handling"""
        try:
            logger.info(f"Processing document {document_id} with {len(text_content)} characters")
            
            # Check if chunks already exist
            existing_chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id
            ).first()
            
            if existing_chunks:
                logger.info(f"Document {document_id} already has chunks, skipping")
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
            
            # Create embeddings in batches
            embeddings = self.create_embeddings(chunks)
            
            if len(embeddings) != len(chunks):
                raise ValueError(f"Embedding count {len(embeddings)} doesn't match chunk count {len(chunks)}")
            
            # Create chunk objects
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
            
            # Batch insert for better performance
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
            logger.info(f"Successfully created {len(chunk_objects)} chunks with embeddings for document {document_id}")
            return chunk_objects
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error chunking and embedding document {document_id}: {e}")
            traceback.print_exc()
            raise
    
    def hybrid_similarity_search(self, db: Session, query: str, document_ids: List[str] = None, 
                                top_k: int = 10) -> List[Dict[str, Any]]:
        """ similarity search with hybrid semantic + keyword matching"""
        try:
            if not query.strip():
                logger.warning("Empty query provided to similarity search")
                return []
            
            # Check cache first
            context_hash = self._hash_content(str(document_ids) if document_ids else "all")
            cache_key = f"{query}:{context_hash}"
            
            cached_result = caching_service.get_query_result(query, context_hash)
            if cached_result is not None:
                logger.info("Retrieved search results from cache")
                return cached_result
            
            # Create query embedding
            query_embedding = self.create_embeddings([query])[0]
            query_terms = self.hybrid_search.preprocess_text(query)
            
            # Build similarity query
            similarity_query = """
                SELECT 
                    id,
                    document_id,
                    chunk_index,
                    content,
                    word_count,
                    extra_metadata,
                    1 - (embedding <=> :query_embedding) as semantic_score
                FROM document_chunks 
            """
            
            params = {"query_embedding": str(query_embedding)}
            
            if document_ids:
                placeholders = ','.join([f':doc_id_{i}' for i in range(len(document_ids))])
                similarity_query += f" WHERE document_id IN ({placeholders})"
                for i, doc_id in enumerate(document_ids):
                    params[f'doc_id_{i}'] = doc_id
            
            similarity_query += f" ORDER BY semantic_score DESC LIMIT :top_k_extended"
            params["top_k_extended"] = min(top_k * 3, 50)  # Get more candidates for re-ranking
            
            result = db.execute(text(similarity_query), params)
            results = result.fetchall()
            
            if not results:
                logger.warning("No results found for similarity search")
                return []
            
            # Calculate hybrid scores
            search_results = []
            corpus_stats = self._get_corpus_stats(db, document_ids)
            
            for row in results:
                semantic_score = float(row.semantic_score)
                
                # Calculate keyword score
                doc_terms = self.hybrid_search.preprocess_text(row.content)
                keyword_score = self.hybrid_search.calculate_bm25_score(
                    query_terms, doc_terms, corpus_stats
                )
                
                # Normalize keyword score (simple min-max normalization)
                keyword_score = min(keyword_score / 10.0, 1.0)  # Rough normalization
                
                # Combine scores
                hybrid_score = self.hybrid_search.hybrid_score(semantic_score, keyword_score)
                
                search_results.append({
                    "id": str(row.id),
                    "document_id": str(row.document_id),
                    "chunk_index": row.chunk_index,
                    "content": row.content,
                    "word_count": row.word_count,
                    "extra_metadata": row.extra_metadata,
                    "semantic_score": semantic_score,
                    "keyword_score": keyword_score,
                    "hybrid_score": hybrid_score
                })
            
            # Sort by hybrid score and apply diversity filtering
            search_results.sort(key=lambda x: x['hybrid_score'], reverse=True)
            diversified_results = self._diversify_results(search_results, top_k)
            
            # Cache results
            caching_service.set_query_result(query, context_hash, diversified_results)
            
            logger.info(f"Hybrid search returned {len(diversified_results)} results for query: {query[:50]}...")
            return diversified_results
            
        except Exception as e:
            logger.error(f"Error in hybrid similarity search: {e}")
            traceback.print_exc()
            return []
    
    def _get_corpus_stats(self, db: Session, document_ids: List[str] = None) -> Dict[str, Any]:
        """Get corpus statistics for BM25 calculation"""
        try:
            if document_ids:
                placeholders = ','.join([f"'{doc_id}'" for doc_id in document_ids])
                query = f"""
                    SELECT AVG(word_count) as avg_length, COUNT(*) as total_docs
                    FROM document_chunks 
                    WHERE document_id IN ({placeholders})
                """
            else:
                query = """
                    SELECT AVG(word_count) as avg_length, COUNT(*) as total_docs
                    FROM document_chunks
                """
            
            result = db.execute(text(query)).fetchone()
            
            return {
                "avg_doc_length": float(result.avg_length) if result.avg_length else 100,
                "total_docs": int(result.total_docs) if result.total_docs else 1
            }
        except Exception as e:
            logger.warning(f"Failed to get corpus stats: {e}")
            return {"avg_doc_length": 100, "total_docs": 1}
    
    def _diversify_results(self, results: List[Dict], target_count: int) -> List[Dict]:
        """Apply diversity filtering to reduce redundant results"""
        if len(results) <= target_count:
            return results
        
        diversified = [results[0]]  # Always include top result
        diversity_threshold = settings.rag.diversity_threshold
        
        for candidate in results[1:]:
            if len(diversified) >= target_count:
                break
            
            is_diverse = True
            for selected in diversified:
                similarity = self._calculate_content_similarity(
                    candidate["content"], selected["content"]
                )
                if similarity > diversity_threshold:
                    is_diverse = False
                    break
            
            if is_diverse:
                diversified.append(candidate)
        
        return diversified
    
    def _calculate_content_similarity(self, content1: str, content2: str) -> float:
        """Calculate simple content similarity for diversity filtering"""
        words1 = set(self.hybrid_search.preprocess_text(content1))
        words2 = set(self.hybrid_search.preprocess_text(content2))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def get_relevant_context(self, db: Session, topic: str, document_ids: List[str] = None, 
                           max_context_length: int = None) -> str:
        """ context retrieval with better aggregation"""
        try:
            if max_context_length is None:
                max_context_length = settings.rag.max_context_length
            
            # Use hybrid search for better retrieval
            search_results = self.hybrid_similarity_search(
                db, topic, document_ids, top_k=settings.rag.retrieval_top_k
            )
            
            if not search_results:
                logger.warning(f"No relevant context found for topic: {topic}")
                return ""
            
            # Filter by similarity threshold
            filtered_results = [
                result for result in search_results 
                if result['hybrid_score'] >= settings.rag.similarity_threshold
            ]
            
            if not filtered_results:
                logger.warning(f"No results above similarity threshold for topic: {topic}")
                # Fall back to top result if nothing passes threshold
                filtered_results = search_results[:1]
            
            # Aggregate context with smart truncation
            context_parts = []
            current_length = 0
            
            for result in filtered_results:
                content = result['content'].strip()
                content_length = len(content)
                
                if current_length + content_length <= max_context_length:
                    context_parts.append(content)
                    current_length += content_length
                else:
                    # Try to fit a truncated version
                    remaining_space = max_context_length - current_length
                    if remaining_space > 100:  # Only if meaningful space left
                        truncated = content[:remaining_space - 3] + "..."
                        context_parts.append(truncated)
                    break
            
            context = "\n\n".join(context_parts)
            
            logger.info(f"Retrieved context of {len(context)} characters from {len(context_parts)} chunks")
            return context
            
        except Exception as e:
            logger.error(f"Error getting relevant context: {e}")
            traceback.print_exc()
            return ""

    def similarity_search(self, db: Session, query: str, document_id: str = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """Backward compatibility wrapper for existing similarity_search calls"""
        document_ids = [document_id] if document_id else None
        return self.hybrid_similarity_search(db, query, document_ids, top_k)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get caching statistics"""
        return caching_service.get_stats()
    
    def cleanup_cache(self) -> Dict[str, int]:
        """Cleanup expired cache entries"""
        return caching_service.cleanup()

vector_processor = VectorProcessor()