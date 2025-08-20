from app.processors.vector_processor import vector_processor
from app.services.monitoring_service import monitoring_service, MonitoredOperation, track_database_operation
from app.services.caching_service import caching_service
import logging
import time

logger = logging.getLogger(__name__)

class VectorService:
    def __init__(self):
        self.vector_processor = vector_processor
    
    def get_relevant_context(self, db, topic: str, document_ids: list = None, max_context_length: int = 4000) -> str:
        with MonitoredOperation("context_retrieval") as op:
            op.add_metadata(
                topic_length=len(topic),
                document_count=len(document_ids) if document_ids else 0,
                max_length=max_context_length
            )
            
            start_time = time.time()
            result = self.vector_processor.get_relevant_context(db, topic, document_ids, max_context_length)
            duration = time.time() - start_time
            
            track_database_operation("vector_search", duration, success=bool(result))
            
            op.add_metadata(
                result_length=len(result),
                retrieval_success=bool(result)
            )
            
            return result
    
    def chunk_and_embed_document(self, db, document_id: str, text_content: str):
        with MonitoredOperation("document_embedding") as op:
            op.add_metadata(
                document_id=document_id,
                content_length=len(text_content),
                word_count=len(text_content.split())
            )
            
            result = self.vector_processor.chunk_and_embed_document(db, document_id, text_content)
            
            op.add_metadata(
                chunks_created=len(result) if result else 0
            )
            
            return result
    
    def similarity_search(self, db, query: str, document_id: str = None, top_k: int = 5):
        with MonitoredOperation("similarity_search") as op:
            op.add_metadata(
                query_length=len(query),
                document_id=document_id,
                top_k=top_k
            )
            
            result = self.vector_processor.similarity_search(db, query, document_id, top_k)
            
            op.add_metadata(
                results_found=len(result) if result else 0
            )
            
            return result
    
    def get_cache_stats(self):
        return self.vector_processor.get_cache_stats()
    
    def cleanup_cache(self):
        return self.vector_processor.cleanup_cache()
    
vector_service = VectorService()