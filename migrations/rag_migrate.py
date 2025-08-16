
import os
from sqlalchemy import create_engine, text
# from app.config import settings
from dotenv import load_dotenv

load_dotenv(override=True)


def setup_pgvector_extension():
    """Setup pgvector extension in PostgreSQL"""
    engine = create_engine(os.getenv("DATABASE_URL"))
    
    with engine.connect() as conn:
        # Enable pgvector extension
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
        print("✓ pgvector extension enabled")

def create_vector_tables():
    """Create new tables with vector support"""
    engine = create_engine(os.getenv("DATABASE_URL"))
    
    with engine.connect() as conn:
        # Create document_chunks table with vector support
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                word_count INTEGER NOT NULL,
                embedding vector(1024),  -- BGE-large-v1.5 dimension
                extra_metadata JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """))
        
        # Create question_generations table for tracking
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS question_generations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_input TEXT NOT NULL,
                context_chunks JSONB NOT NULL,
                generation_parameters JSONB,
                output_questions JSONB,
                final_questions JSONB,
                model_version VARCHAR(100),
                generation_status VARCHAR(50) DEFAULT 'processing',
                retry_count INTEGER DEFAULT 0,
                human_review_status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """))
        
        conn.commit()
        print("✓ Vector tables created")

def add_new_columns():
    """Add new columns to existing tables"""
    engine = create_engine(os.getenv("DATABASE_URL"))
    
    with engine.connect() as conn:
        # Add new columns to questions table
        try:
            conn.execute(text("ALTER TABLE questions ADD COLUMN IF NOT EXISTS topic VARCHAR(255);"))
            conn.execute(text("ALTER TABLE questions ADD COLUMN IF NOT EXISTS source_context TEXT;"))
            conn.execute(text("ALTER TABLE questions ADD COLUMN IF NOT EXISTS generation_model VARCHAR(100);"))
            conn.execute(text("ALTER TABLE questions ADD COLUMN IF NOT EXISTS validation_score FLOAT;"))
            conn.execute(text("ALTER TABLE questions ADD COLUMN IF NOT EXISTS human_validated BOOLEAN DEFAULT FALSE;"))
            print("✓ Questions table columns added")
        except Exception as e:
            print(f"Questions table update: {e}")
        
        # Add new columns to flashcards table
        try:
            conn.execute(text("ALTER TABLE flashcards ADD COLUMN IF NOT EXISTS topic VARCHAR(255);"))
            conn.execute(text("ALTER TABLE flashcards ADD COLUMN IF NOT EXISTS source_context TEXT;"))
            conn.execute(text("ALTER TABLE flashcards ADD COLUMN IF NOT EXISTS generation_model VARCHAR(100);"))
            conn.execute(text("ALTER TABLE flashcards ADD COLUMN IF NOT EXISTS validation_score FLOAT;"))
            conn.execute(text("ALTER TABLE flashcards ADD COLUMN IF NOT EXISTS human_validated BOOLEAN DEFAULT FALSE;"))
            print("✓ Flashcards table columns added")
        except Exception as e:
            print(f"Flashcards table update: {e}")
        
        # Add explanation column to question_answers
        try:
            conn.execute(text("ALTER TABLE question_answers ADD COLUMN IF NOT EXISTS explanation TEXT;"))
            print("✓ Question answers table updated")
        except Exception as e:
            print(f"Question answers table update: {e}")
        
        conn.commit()

def create_indexes():
    """Create indexes for better performance"""
    engine = create_engine(os.getenv("DATABASE_URL"))
    
    with engine.connect() as conn:
        # Vector similarity index
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding 
            ON document_chunks USING ivfflat (embedding vector_cosine_ops) 
            WITH (lists = 100);
        """))
        
        # Document chunks indexes
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_document_chunks_chunk_index ON document_chunks(chunk_index);"))
        
        # Question generations indexes
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_question_generations_status ON question_generations(generation_status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_question_generations_review_status ON question_generations(human_review_status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_question_generations_created_at ON question_generations(created_at);"))
        
        # Enhanced indexes for existing tables
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_questions_validation_score ON questions(validation_score);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_questions_human_validated ON questions(human_validated);"))
        
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_flashcards_topic ON flashcards(topic);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_flashcards_validation_score ON flashcards(validation_score);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_flashcards_human_validated ON flashcards(human_validated);"))
        
        conn.commit()
        print("✓ Indexes created")

def run_migration():
    """Run the complete migration"""
    try:
        print("Starting database migration...")
        
        # Step 1: Setup pgvector extension
        setup_pgvector_extension()
        
        # Step 2: Create new tables
        create_vector_tables()
        
        # Step 3: Add new columns to existing tables
        add_new_columns()
        
        # Step 4: Create indexes
        create_indexes()
        
        print("✅ Migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    # Before running this script, make sure pgvector is installed in PostgreSQL:
    # 1. Install pgvector extension in your PostgreSQL database
    # 2. Run: CREATE EXTENSION vector;
    
    run_migration()