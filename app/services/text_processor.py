from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import pipeline
import traceback

class ChunkSummarizeService:
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
    
    def summarize_chunk(self, text, max_length=300, min_length=100):
        try:
            if len(text.split()) < 20:
                return text
                
            result = self.summarizer(
                text,
                max_length=max_length,
                min_length=min_length,
                do_sample=False,
                truncation=True
            )
            return result[0]['summary_text']
        except Exception as e:
            traceback.print_exc()
            sentences = text.split('. ')
            return '. '.join(sentences[:3]) + '.'
    
    def process_text(self, document_text: str, target_chunks: int = 5):
        word_count = len(document_text.split())
        text_splitter = self.setup_text_splitter(word_count, target_chunks)
        chunks = text_splitter.split_text(document_text)

        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            summary = self.summarize_chunk(chunk)
            chunk_summaries.append({
                "chunk_number": i+1,
                "chunk_text": chunk,
                "summary": summary
            })

        combined_summaries = " ".join([cs["summary"] for cs in chunk_summaries])
        global_summary = self.summarize_chunk(combined_summaries, max_length=400, min_length=200)
        
        return {
            "original_word_count": word_count,
            "num_chunks": len(chunks),
            "chunk_summaries": chunk_summaries,
            "global_summary": global_summary
        }

chunk_service = ChunkSummarizeService()