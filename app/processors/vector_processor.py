import numpy as np
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models import DocumentChunk, Document
from app.processors.chunk_processor import chunk_processor
import traceback
import logging
import uuid

logger = logging.getLogger(__name__)

class VectorProcessor:
    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5"):
        """Initialize with BGE-large-v1.5 model for high-quality embeddings"""
        self.model = SentenceTransformer(model_name)
        self.embedding_dimension = 1024
    
    def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Create embeddings for a list of texts"""
        try:
            embeddings = self.model.encode(texts, normalize_embeddings=True)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Error creating embeddings: {e}")
            traceback.print_exc()
            raise
    
    def chunk_and_embed_document(self, db: Session, document_id: str, text_content: str) -> List[DocumentChunk]:
        """Chunk document and create embeddings for each chunk"""
        try:
            word_count = len(text_content.split())
            text_splitter = chunk_processor.setup_text_splitter(word_count)
            chunks = text_splitter.split_text(text_content)
            
            embeddings = self.create_embeddings(chunks)
            
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
                        "word_count": len(chunk_text.split())
                    }
                )
                db.add(chunk_obj)
                chunk_objects.append(chunk_obj)
            
            db.commit()
            logger.info(f"Created {len(chunk_objects)} chunks with embeddings for document {document_id}")
            return chunk_objects
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error chunking and embedding document {document_id}: {e}")
            traceback.print_exc()
            raise
    
    def similarity_search(self, db: Session, query: str, document_id: str = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """Perform similarity search using cosine similarity"""
        try:
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
            
            if document_id:
                similarity_query += " WHERE document_id = :document_id"
                params["document_id"] = document_id
            
            similarity_query += " ORDER BY similarity_score DESC LIMIT :top_k"
            params["top_k"] = top_k
            
            result = db.execute(text(similarity_query), params)
            results = result.fetchall()
            
            search_results = []
            for row in results:
                search_results.append({
                    "id": str(row.id),
                    "document_id": str(row.document_id),
                    "chunk_index": row.chunk_index,
                    "content": row.content,
                    "word_count": row.word_count,
                    "extra_metadata": row.extra_metadata,
                    "similarity_score": float(row.similarity_score)
                })
            
            return search_results
            
        except Exception as e:
            logger.error(f"Error in similarity search: {e}")
            traceback.print_exc()
            raise
    
    def get_relevant_context(self, db: Session, topic: str, document_ids: List[str] = None, max_context_length: int = 4000) -> str:
        """Get relevant context for a topic by combining top matching chunks"""
        try:
            all_results = []
            
            if document_ids:
                for doc_id in document_ids:
                    results = self.similarity_search(db, topic, doc_id, top_k=3)
                    all_results.extend(results)
            else:
                all_results = self.similarity_search(db, topic, top_k=10)
            
            all_results.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            context_parts = []
            current_length = 0
            
            for result in all_results:
                content = result['content']
                if current_length + len(content) <= max_context_length:
                    context_parts.append(content)
                    current_length += len(content)
                else:
                    remaining_space = max_context_length - current_length
                    if remaining_space > 100:
                        context_parts.append(content[:remaining_space] + "...")
                    break
            
            return "\n\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"Error getting relevant context: {e}")
            traceback.print_exc()
            raise

vector_processor = VectorProcessor()