# app/services/caching_service.py
import hashlib
import json
import pickle
import os
import time
from typing import Any, Optional, List, Dict
from datetime import datetime, timedelta
import logging
from app.config import settings

logger = logging.getLogger(__name__)

class CacheEntry:
    def __init__(self, value: Any, ttl: int):
        self.value = value
        self.created_at = time.time()
        self.ttl = ttl
        self.access_count = 0
        self.last_accessed = time.time()
    
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl
    
    def access(self) -> Any:
        self.access_count += 1
        self.last_accessed = time.time()
        return self.value

class InMemoryCache:
    """Thread-safe in-memory cache with LRU eviction"""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: Dict[str, CacheEntry] = {}
        self._lock = None  # Would use threading.Lock() in production
    
    def get(self, key: str) -> Optional[Any]:
        if key not in self.cache:
            return None
        
        entry = self.cache[key]
        if entry.is_expired():
            del self.cache[key]
            return None
        
        return entry.access()
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if ttl is None:
            ttl = self.default_ttl
        
        # Evict if at capacity
        if len(self.cache) >= self.max_size:
            self._evict_lru()
        
        self.cache[key] = CacheEntry(value, ttl)
    
    def delete(self, key: str) -> bool:
        return self.cache.pop(key, None) is not None
    
    def clear(self) -> None:
        self.cache.clear()
    
    def _evict_lru(self) -> None:
        """Evict least recently used entry"""
        if not self.cache:
            return
        
        lru_key = min(
            self.cache.keys(),
            key=lambda k: self.cache[k].last_accessed
        )
        del self.cache[lru_key]
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_entries = len(self.cache)
        expired_entries = sum(1 for entry in self.cache.values() if entry.is_expired())
        
        return {
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "active_entries": total_entries - expired_entries,
            "cache_utilization": total_entries / self.max_size if self.max_size > 0 else 0
        }

class PersistentCache:
    """File-based persistent cache for embeddings"""
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.embeddings_dir = os.path.join(cache_dir, "embeddings")
        self.queries_dir = os.path.join(cache_dir, "queries")
        os.makedirs(self.embeddings_dir, exist_ok=True)
        os.makedirs(self.queries_dir, exist_ok=True)
    
    def _get_cache_path(self, key: str, cache_type: str = "embeddings") -> str:
        """Get file path for cache key"""
        cache_dir = self.embeddings_dir if cache_type == "embeddings" else self.queries_dir
        return os.path.join(cache_dir, f"{key}.pkl")
    
    def _hash_key(self, content: str) -> str:
        """Create hash for content"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get cached embedding for text"""
        key = self._hash_key(text)
        cache_path = self._get_cache_path(key, "embeddings")
        
        if not os.path.exists(cache_path):
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                cached_data = pickle.load(f)
            
            # Check if cache is expired
            if time.time() - cached_data['timestamp'] > settings.rag.cache_ttl_seconds:
                os.remove(cache_path)
                return None
            
            return cached_data['embedding']
        
        except Exception as e:
            logger.warning(f"Failed to load cached embedding: {e}")
            return None
    
    def set_embedding(self, text: str, embedding: List[float]) -> None:
        """Cache embedding for text"""
        key = self._hash_key(text)
        cache_path = self._get_cache_path(key, "embeddings")
        
        try:
            cache_data = {
                'text': text[:100],  # Store first 100 chars for debugging
                'embedding': embedding,
                'timestamp': time.time()
            }
            
            with open(cache_path, 'wb') as f:
                pickle.dump(cache_data, f)
        
        except Exception as e:
            logger.warning(f"Failed to cache embedding: {e}")
    
    def get_query_result(self, query: str, context_hash: str) -> Optional[Dict]:
        """Get cached query result"""
        key = self._hash_key(f"{query}:{context_hash}")
        cache_path = self._get_cache_path(key, "queries")
        
        if not os.path.exists(cache_path):
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                cached_data = pickle.load(f)
            
            if time.time() - cached_data['timestamp'] > settings.rag.cache_ttl_seconds:
                os.remove(cache_path)
                return None
            
            return cached_data['result']
        
        except Exception as e:
            logger.warning(f"Failed to load cached query result: {e}")
            return None
    
    def set_query_result(self, query: str, context_hash: str, result: Dict) -> None:
        """Cache query result"""
        key = self._hash_key(f"{query}:{context_hash}")
        cache_path = self._get_cache_path(key, "queries")
        
        try:
            cache_data = {
                'query': query,
                'context_hash': context_hash,
                'result': result,
                'timestamp': time.time()
            }
            
            with open(cache_path, 'wb') as f:
                pickle.dump(cache_data, f)
        
        except Exception as e:
            logger.warning(f"Failed to cache query result: {e}")
    
    def cleanup_expired(self) -> int:
        """Remove expired cache files"""
        removed_count = 0
        current_time = time.time()
        
        for cache_type in ["embeddings", "queries"]:
            cache_dir = self.embeddings_dir if cache_type == "embeddings" else self.queries_dir
            
            for filename in os.listdir(cache_dir):
                if not filename.endswith('.pkl'):
                    continue
                
                file_path = os.path.join(cache_dir, filename)
                try:
                    with open(file_path, 'rb') as f:
                        cached_data = pickle.load(f)
                    
                    if current_time - cached_data['timestamp'] > settings.rag.cache_ttl_seconds:
                        os.remove(file_path)
                        removed_count += 1
                
                except Exception as e:
                    logger.warning(f"Failed to check cache file {file_path}: {e}")
                    # Remove corrupted files
                    try:
                        os.remove(file_path)
                        removed_count += 1
                    except:
                        pass
        
        return removed_count

class CachingService:
    """Unified caching service"""
    
    def __init__(self):
        self.memory_cache = InMemoryCache(
            max_size=settings.rag.max_cache_size,
            default_ttl=settings.rag.cache_ttl_seconds
        )
        self.persistent_cache = PersistentCache(settings.cache_dir)
        self.stats = {
            "memory_hits": 0,
            "memory_misses": 0,
            "persistent_hits": 0,
            "persistent_misses": 0,
            "cache_writes": 0
        }
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding with multi-level caching"""
        # Try memory cache first
        memory_result = self.memory_cache.get(f"emb:{text}")
        if memory_result is not None:
            self.stats["memory_hits"] += 1
            return memory_result
        
        self.stats["memory_misses"] += 1
        
        # Try persistent cache
        persistent_result = self.persistent_cache.get_embedding(text)
        if persistent_result is not None:
            # Store in memory cache for faster future access
            self.memory_cache.set(f"emb:{text}", persistent_result)
            self.stats["persistent_hits"] += 1
            return persistent_result
        
        self.stats["persistent_misses"] += 1
        return None
    
    def set_embedding(self, text: str, embedding: List[float]) -> None:
        """Cache embedding at both levels"""
        self.memory_cache.set(f"emb:{text}", embedding)
        self.persistent_cache.set_embedding(text, embedding)
        self.stats["cache_writes"] += 1
    
    def get_query_result(self, query: str, context_hash: str) -> Optional[Dict]:
        """Get cached query result"""
        cache_key = f"query:{query}:{context_hash}"
        
        # Try memory cache first
        memory_result = self.memory_cache.get(cache_key)
        if memory_result is not None:
            self.stats["memory_hits"] += 1
            return memory_result
        
        self.stats["memory_misses"] += 1
        
        # Try persistent cache
        persistent_result = self.persistent_cache.get_query_result(query, context_hash)
        if persistent_result is not None:
            self.memory_cache.set(cache_key, persistent_result)
            self.stats["persistent_hits"] += 1
            return persistent_result
        
        self.stats["persistent_misses"] += 1
        return None
    
    def set_query_result(self, query: str, context_hash: str, result: Dict) -> None:
        """Cache query result"""
        cache_key = f"query:{query}:{context_hash}"
        self.memory_cache.set(cache_key, result)
        self.persistent_cache.set_query_result(query, context_hash, result)
        self.stats["cache_writes"] += 1
    
    def cleanup(self) -> Dict[str, int]:
        """Cleanup expired cache entries"""
        memory_stats = self.memory_cache.stats()
        persistent_removed = self.persistent_cache.cleanup_expired()
        
        return {
            "memory_entries": memory_stats["active_entries"],
            "persistent_removed": persistent_removed
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        memory_stats = self.memory_cache.stats()
        
        total_requests = (
            self.stats["memory_hits"] + self.stats["memory_misses"]
        )
        
        hit_rate = (
            self.stats["memory_hits"] + self.stats["persistent_hits"]
        ) / max(total_requests, 1)
        
        return {
            "memory_cache": memory_stats,
            "hit_rate": hit_rate,
            "total_requests": total_requests,
            **self.stats
        }

# Global cache instance
caching_service = CachingService()