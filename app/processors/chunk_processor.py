from langchain_text_splitters import RecursiveCharacterTextSplitter

class ChunkProcessor:
    def __init__(self):
        pass

    def setup_text_splitter(self, document_length: int):
        estimated_chars = document_length * 6  

        if estimated_chars <= 2000:
            chunk_size = 800
            chunk_overlap = 100
        elif estimated_chars <= 8000:
            chunk_size = 1500
            chunk_overlap = 150
        elif estimated_chars <= 20000:
            chunk_size = 2500
            chunk_overlap = 200
        else:
            chunk_size = 3500
            chunk_overlap = 300

        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )    

chunk_processor = ChunkProcessor()