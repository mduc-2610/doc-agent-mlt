from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config import settings

class ChunkProcessor:
    def __init__(self):
        self.chunk_config = settings.chunk

    def setup_text_splitter(self, document_length: int):
        estimated_chars = document_length * self.chunk_config.chars_per_token_estimate

        if estimated_chars <= self.chunk_config.small_doc_threshold:
            chunk_size = self.chunk_config.small_doc_chunk_size
            chunk_overlap = self.chunk_config.small_doc_chunk_overlap
        elif estimated_chars <= self.chunk_config.medium_doc_threshold:
            chunk_size = self.chunk_config.medium_doc_chunk_size
            chunk_overlap = self.chunk_config.medium_doc_chunk_overlap
        elif estimated_chars <= self.chunk_config.large_doc_threshold:
            chunk_size = self.chunk_config.large_doc_chunk_size
            chunk_overlap = self.chunk_config.large_doc_chunk_overlap
        else:
            chunk_size = self.chunk_config.xlarge_doc_chunk_size
            chunk_overlap = self.chunk_config.xlarge_doc_chunk_overlap

        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=self.chunk_config.text_separators
        )    

chunk_processor = ChunkProcessor()