from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import pipeline
import traceback

class ChunkService:
    def __init__(self, model_name="facebook/bart-large-cnn"):
        self.summarizer = pipeline("summarization", model=model_name)
    
    def setup_text_splitter(self, document_length, target_chunks=5):
        estimated_chars = document_length * 6
        base_chunk_size = estimated_chars // target_chunks
        
        if base_chunk_size > 4000:
            chunk_size = 4000
            chunk_overlap = 200
        elif base_chunk_size > 2000:
            chunk_size = base_chunk_size
            chunk_overlap = base_chunk_size // 20
        else:
            chunk_size = max(1000, base_chunk_size)
            chunk_overlap = chunk_size // 10
            
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
    

chunk_service = ChunkService()