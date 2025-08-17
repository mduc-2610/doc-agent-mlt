from app.processors.vector_processor import vector_processor

class VectorService:
    def __init__(self):
        self.vector_processor = vector_processor
    
    def get_relevant_context(self, db, topic: str, document_ids: list = None, max_context_length: int = 4000) -> str:
        return self.vector_processor.get_relevant_context(db, topic, document_ids, max_context_length)
    
    def chunk_and_embed_document(self, db, document_id: str, text_content: str):
        return self.vector_processor.chunk_and_embed_document(db, document_id, text_content)
    
    def similarity_search(self, db, query: str, document_id: str = None, top_k: int = 5):
        return self.vector_processor.similarity_search(db, query, document_id, top_k)

# Global instance
vector_service = VectorService()