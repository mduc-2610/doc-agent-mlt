"""
Reset Data Script - Comprehensive cleanup and database reset utility

This script performs the following operations:
1. Deletes all files and directories from local storage
2. Deletes all buckets and objects from MinIO storage  
3. Drops and recreates the PostgreSQL database
4. Creates necessary database extensions
5. Recreates database tables

Usage:
    python reset_data.py [--confirm] [--storage-only] [--db-only]
    
Options:
    --confirm       Skip confirmation prompt
    --storage-only  Only clean storage, skip database operations
    --db-only       Only reset database, skip storage cleanup
"""

import os
import sys
import shutil
import logging
import argparse
import asyncio
from typing import List, Optional
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from app.storages.factory import get_storage_provider
from app.storages.local_provider import LocalStorageProvider
from app.storages.minio_provider import MinIOStorageProvider

# Database imports
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from app.models.base import Base

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DataResetManager:
    """Manages the complete reset of storage and database"""
    
    def __init__(self):
        self.dir_mapping = {
            "content": "dc-ag-content-files",
            "source": "dc-ag-source-files", 
            "tmp": "dc-ag-tmp-files",
            "summary": "dc-ag-summary-files"
        }
        
    async def reset_all(self, storage_only: bool = False, db_only: bool = False):
        """Reset both storage and database"""
        try:
            if not db_only:
                logger.info("🧹 Starting storage cleanup...")
                await self.cleanup_storage()
                
            if not storage_only:
                logger.info("🗄️ Starting database reset...")
                await self.reset_database()
                
            logger.info("✅ Reset completed successfully!")
            
        except Exception as e:
            logger.error(f"❌ Reset failed: {e}")
            raise
    
    async def cleanup_storage(self):
        """Clean up all storage providers"""
        logger.info("Cleaning up local storage...")
        await self.cleanup_local_storage()
        
        logger.info("Cleaning up MinIO storage...")
        await self.cleanup_minio_storage()
        
    async def cleanup_local_storage(self):
        """Delete all local storage directories and files"""
        try:
            base_dir = Path(settings.storage.local_path)
            
            if not base_dir.exists():
                logger.info(f"Local storage directory {base_dir} doesn't exist")
                return
                
            logger.info(f"Removing local storage directory: {base_dir}")
            
            # List all directories before deletion
            if base_dir.exists():
                subdirs = [d for d in base_dir.iterdir() if d.is_dir()]
                files = [f for f in base_dir.iterdir() if f.is_file()]
                
                logger.info(f"Found {len(subdirs)} directories and {len(files)} files")
                for subdir in subdirs:
                    logger.info(f"  Directory: {subdir.name}")
                for file in files:
                    logger.info(f"  File: {file.name}")
            
            # Remove the entire local storage directory
            if base_dir.exists():
                shutil.rmtree(base_dir)
                logger.info("✅ Local storage cleaned successfully")
            
            # Recreate base directory structure
            logger.info("Recreating local storage structure...")
            for directory in self.dir_mapping.values():
                dir_path = base_dir / directory
                dir_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created directory: {dir_path}")
                
        except Exception as e:
            logger.error(f"Failed to cleanup local storage: {e}")
            raise
    
    async def cleanup_minio_storage(self):
        """Delete all MinIO buckets and objects"""
        try:
            # Create MinIO provider to access client
            minio_provider = MinIOStorageProvider()
            client = minio_provider.client
            
            logger.info("Listing all MinIO buckets...")
            
            # List all buckets
            buckets = client.list_buckets()
            bucket_names = [bucket.name for bucket in buckets]
            
            if not bucket_names:
                logger.info("No MinIO buckets found")
                return
                
            logger.info(f"Found {len(bucket_names)} buckets: {bucket_names}")
            
            # Delete all objects in each bucket, then delete the bucket
            for bucket_name in bucket_names:
                try:
                    logger.info(f"Processing bucket: {bucket_name}")
                    
                    # List all objects in the bucket
                    objects = client.list_objects(bucket_name, recursive=True)
                    object_names = [obj.object_name for obj in objects]
                    
                    if object_names:
                        logger.info(f"Found {len(object_names)} objects in {bucket_name}")
                        
                        # Delete all objects
                        for obj_name in object_names:
                            client.remove_object(bucket_name, obj_name)
                            logger.info(f"  Deleted object: {obj_name}")
                    else:
                        logger.info(f"No objects found in bucket: {bucket_name}")
                    
                    # Delete the bucket
                    client.remove_bucket(bucket_name)
                    logger.info(f"✅ Deleted bucket: {bucket_name}")
                    
                except Exception as e:
                    logger.error(f"Failed to delete bucket {bucket_name}: {e}")
                    continue
            
            # Recreate the standard buckets
            logger.info("Recreating standard MinIO buckets...")
            for directory in self.dir_mapping.values():
                try:
                    if not client.bucket_exists(directory):
                        client.make_bucket(directory)
                        logger.info(f"Created bucket: {directory}")
                    else:
                        logger.info(f"Bucket already exists: {directory}")
                except Exception as e:
                    logger.error(f"Failed to create bucket {directory}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to cleanup MinIO storage: {e}")
            raise
    
    async def reset_database(self):
        """Drop and recreate the database with extensions"""
        try:
            db_name = settings.database.aws_db_name if settings.database.use_aws_db else settings.database.local_db_name
            
            logger.info(f"Resetting database: {db_name}")
            
            # Get connection parameters
            if settings.database.use_aws_db:
                conn_params = {
                    'host': settings.database.aws_db_host,
                    'port': settings.database.aws_db_port,
                    'user': settings.database.aws_db_user,
                    'password': settings.database.aws_db_password,
                }
            else:
                conn_params = {
                    'host': settings.database.local_db_host,
                    'port': settings.database.local_db_port,
                    'user': settings.database.local_db_user,
                    'password': settings.database.local_db_password,
                }
            
            # Connect to PostgreSQL server (not to the specific database)
            logger.info("Connecting to PostgreSQL server...")
            admin_conn = psycopg2.connect(
                database='postgres',  # Connect to default postgres database
                **conn_params
            )
            admin_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            
            with admin_conn.cursor() as cursor:
                # Terminate existing connections to the database
                logger.info(f"Terminating existing connections to {db_name}...")
                cursor.execute(f"""
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = %s
                    AND pid <> pg_backend_pid()
                """, (db_name,))
                
                # Drop the database if it exists
                logger.info(f"Dropping database {db_name}...")
                cursor.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
                
                # Create the database
                logger.info(f"Creating database {db_name}...")
                cursor.execute(f'CREATE DATABASE "{db_name}"')
                
            admin_conn.close()
            
            # Connect to the new database to create extensions
            logger.info("Creating database extensions...")
            db_conn = psycopg2.connect(
                database=db_name,
                **conn_params
            )
            db_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            
            with db_conn.cursor() as cursor:
                # Create commonly used extensions
                extensions = [
                    'uuid-ossp',      # UUID generation
                    'pg_trgm',        # Trigram matching for text search
                    'btree_gin',      # GIN index support for btree operations
                    'btree_gist',     # GiST index support for btree operations
                ]
                
                for ext in extensions:
                    try:
                        cursor.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')
                        logger.info(f"✅ Created extension: {ext}")
                    except Exception as e:
                        logger.warning(f"Could not create extension {ext}: {e}")
                
                # Create vector extension if available (for embedding storage)
                try:
                    cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
                    logger.info("✅ Created extension: vector")
                except Exception as e:
                    logger.warning(f"Vector extension not available: {e}")
            
            db_conn.close()
            
            # Create tables using SQLAlchemy
            logger.info("Creating database tables...")
            await self.create_tables()
            
            logger.info("✅ Database reset completed successfully")
            
        except Exception as e:
            logger.error(f"Failed to reset database: {e}")
            raise
    
    async def create_tables(self):
        """Create all database tables"""
        try:
            # Import all models to ensure they're registered with Base
            from app.models import document, question, session
            
            # Create engine for the new database
            engine = create_engine(settings.database.get_database_url())
            
            # Create all tables
            Base.metadata.create_all(bind=engine)
            
            # Test the connection
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
            
            logger.info("✅ All tables created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise

def confirm_reset():
    """Ask user for confirmation before proceeding with reset"""
    print("\n⚠️  WARNING: This will permanently delete ALL data!")
    print("This includes:")
    print("  • All files in local storage")
    print("  • All objects and buckets in MinIO")
    print("  • Complete database with all tables and data")
    print()
    
    response = input("Are you sure you want to continue? Type 'YES' to confirm: ")
    return response == 'YES'

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Reset all data and storage')
    parser.add_argument('--confirm', action='store_true', 
                       help='Skip confirmation prompt')
    parser.add_argument('--storage-only', action='store_true',
                       help='Only clean storage, skip database operations')
    parser.add_argument('--db-only', action='store_true',
                       help='Only reset database, skip storage cleanup')
    
    args = parser.parse_args()
    
    if args.storage_only and args.db_only:
        logger.error("Cannot specify both --storage-only and --db-only")
        sys.exit(1)
    
    # Confirmation check
    if not args.confirm and not confirm_reset():
        logger.info("Reset cancelled by user")
        return
    
    try:
        reset_manager = DataResetManager()
        await reset_manager.reset_all(
            storage_only=args.storage_only,
            db_only=args.db_only
        )
        
    except KeyboardInterrupt:
        logger.info("Reset cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Reset failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())