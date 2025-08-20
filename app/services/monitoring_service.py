# app/services/monitoring_service.py
import time
import psutil
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import deque, defaultdict
import logging
from dataclasses import dataclass, asdict
from app.config import settings

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetric:
    """Individual performance metric"""
    name: str
    value: float
    timestamp: datetime
    tags: Dict[str, str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class RequestMetrics:
    """Metrics for individual requests"""
    endpoint: str
    method: str
    duration: float
    status_code: int
    timestamp: datetime
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class CircularBuffer:
    """Thread-safe circular buffer for metrics"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.data = deque(maxlen=max_size)
        self.lock = threading.Lock()
    
    def append(self, item):
        with self.lock:
            self.data.append(item)
    
    def get_recent(self, count: int = None) -> List:
        with self.lock:
            if count is None:
                return list(self.data)
            return list(self.data)[-count:]
    
    def get_since(self, since: datetime) -> List:
        with self.lock:
            return [item for item in self.data if item.timestamp >= since]
    
    def clear(self):
        with self.lock:
            self.data.clear()

class SystemMonitor:
    """Monitor system resources"""
    
    def __init__(self):
        self.metrics_buffer = CircularBuffer(max_size=1440)  # 24 hours at 1-minute intervals
        self.monitoring = False
        self.monitor_thread = None
    
    def start_monitoring(self, interval: int = 60):
        """Start system monitoring"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True
        )
        self.monitor_thread.start()
        logger.info("System monitoring started")
    
    def stop_monitoring(self):
        """Stop system monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
        logger.info("System monitoring stopped")
    
    def _monitor_loop(self, interval: int):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                metrics = self._collect_system_metrics()
                for metric in metrics:
                    self.metrics_buffer.append(metric)
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(interval)
    
    def _collect_system_metrics(self) -> List[PerformanceMetric]:
        """Collect current system metrics"""
        timestamp = datetime.now()
        metrics = []
        
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent()
            metrics.append(PerformanceMetric("cpu_usage_percent", cpu_percent, timestamp))
            
            # Memory metrics
            memory = psutil.virtual_memory()
            metrics.append(PerformanceMetric("memory_usage_percent", memory.percent, timestamp))
            metrics.append(PerformanceMetric("memory_available_gb", memory.available / (1024**3), timestamp))
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            metrics.append(PerformanceMetric("disk_usage_percent", disk.percent, timestamp))
            metrics.append(PerformanceMetric("disk_free_gb", disk.free / (1024**3), timestamp))
            
            # Network metrics (if available)
            try:
                network = psutil.net_io_counters()
                metrics.append(PerformanceMetric("network_bytes_sent", network.bytes_sent, timestamp))
                metrics.append(PerformanceMetric("network_bytes_recv", network.bytes_recv, timestamp))
            except:
                pass  # Network metrics not available on all systems
            
        except Exception as e:
            logger.warning(f"Failed to collect some system metrics: {e}")
        
        return metrics
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current system metrics"""
        metrics = self._collect_system_metrics()
        return {metric.name: metric.value for metric in metrics}
    
    def get_metrics_history(self, hours: int = 1) -> Dict[str, List[Dict]]:
        """Get metrics history for specified hours"""
        since = datetime.now() - timedelta(hours=hours)
        recent_metrics = self.metrics_buffer.get_since(since)
        
        # Group by metric name
        grouped = defaultdict(list)
        for metric in recent_metrics:
            grouped[metric.name].append(metric.to_dict())
        
        return dict(grouped)

class ApplicationMonitor:
    """Monitor application-specific metrics"""
    
    def __init__(self):
        self.request_metrics = CircularBuffer(max_size=10000)
        self.generation_metrics = CircularBuffer(max_size=1000)
        self.error_metrics = CircularBuffer(max_size=1000)
        
        # Counters
        self.counters = defaultdict(int)
        self.timers = defaultdict(list)
        
        # Lock for thread safety
        self.lock = threading.Lock()
    
    def record_request(self, endpoint: str, method: str, duration: float, 
                      status_code: int, user_id: str = None, session_id: str = None):
        """Record request metrics"""
        metric = RequestMetrics(
            endpoint=endpoint,
            method=method,
            duration=duration,
            status_code=status_code,
            timestamp=datetime.now(),
            user_id=user_id,
            session_id=session_id
        )
        self.request_metrics.append(metric)
        
        # Update counters
        with self.lock:
            self.counters[f"requests_{endpoint}"] += 1
            self.counters[f"requests_status_{status_code}"] += 1
            self.timers[f"response_time_{endpoint}"].append(duration)
    
    def record_generation_event(self, event_type: str, duration: float = None, 
                               success: bool = True, metadata: Dict = None):
        """Record content generation events"""
        metric = PerformanceMetric(
            name=f"generation_{event_type}",
            value=duration if duration is not None else 1,
            timestamp=datetime.now(),
            tags={
                "success": str(success),
                **(metadata or {})
            }
        )
        self.generation_metrics.append(metric)
        
        with self.lock:
            self.counters[f"generation_{event_type}"] += 1
            if success:
                self.counters[f"generation_{event_type}_success"] += 1
            else:
                self.counters[f"generation_{event_type}_failure"] += 1
    
    def record_error(self, error_type: str, endpoint: str = None, details: str = None):
        """Record error events"""
        metric = PerformanceMetric(
            name=f"error_{error_type}",
            value=1,
            timestamp=datetime.now(),
            tags={
                "endpoint": endpoint or "unknown",
                "details": details or ""
            }
        )
        self.error_metrics.append(metric)
        
        with self.lock:
            self.counters[f"errors_{error_type}"] += 1
    
    def get_request_stats(self, hours: int = 1) -> Dict[str, Any]:
        """Get request statistics"""
        since = datetime.now() - timedelta(hours=hours)
        recent_requests = self.request_metrics.get_since(since)
        
        if not recent_requests:
            return {"message": "No recent requests"}
        
        durations = [r.duration for r in recent_requests]
        status_codes = [r.status_code for r in recent_requests]
        
        stats = {
            "total_requests": len(recent_requests),
            "avg_response_time": sum(durations) / len(durations),
            "min_response_time": min(durations),
            "max_response_time": max(durations),
            "success_rate": len([s for s in status_codes if 200 <= s < 300]) / len(status_codes),
            "error_rate": len([s for s in status_codes if s >= 400]) / len(status_codes),
            "requests_per_hour": len(recent_requests) / hours
        }
        
        endpoint_stats = defaultdict(list)
        for request in recent_requests:
            endpoint_stats[request.endpoint].append(request.duration)
        
        stats["by_endpoint"] = {
            endpoint: {
                "count": len(durations),
                "avg_duration": sum(durations) / len(durations)
            }
            for endpoint, durations in endpoint_stats.items()
        }
        
        return stats
    
    def get_generation_stats(self, hours: int = 1) -> Dict[str, Any]:
        """Get content generation statistics"""
        since = datetime.now() - timedelta(hours=hours)
        recent_generations = self.generation_metrics.get_since(since)
        
        if not recent_generations:
            return {"message": "No recent generations"}
        
        # Group by generation type
        by_type = defaultdict(list)
        for gen in recent_generations:
            gen_type = gen.name.replace("generation_", "")
            by_type[gen_type].append(gen)
        
        stats = {}
        for gen_type, generations in by_type.items():
            successful = [g for g in generations if g.tags and g.tags.get("success") == "True"]
            
            stats[gen_type] = {
                "total_attempts": len(generations),
                "successful": len(successful),
                "success_rate": len(successful) / len(generations) if generations else 0,
                "avg_duration": sum(g.value for g in successful) / len(successful) if successful else 0
            }
        
        return stats
    
    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get error summary"""
        since = datetime.now() - timedelta(hours=hours)
        recent_errors = self.error_metrics.get_since(since)
        
        # Group by error type
        error_counts = defaultdict(int)
        for error in recent_errors:
            error_type = error.name.replace("error_", "")
            error_counts[error_type] += 1
        
        return {
            "total_errors": len(recent_errors),
            "error_rate_per_hour": len(recent_errors) / hours,
            "by_type": dict(error_counts),
            "recent_errors": [error.to_dict() for error in recent_errors[-10:]]  # Last 10 errors
        }

class MonitoringService:
    """Main monitoring service that coordinates all monitoring"""
    
    def __init__(self):
        self.system_monitor = SystemMonitor()
        self.app_monitor = ApplicationMonitor()
        self.start_time = datetime.now()
        
        # Performance thresholds
        self.thresholds = {
            "cpu_usage_critical": 90.0,
            "memory_usage_critical": 90.0,
            "disk_usage_critical": 95.0,
            "response_time_slow": 5.0,
            "error_rate_high": 0.1  # 10%
        }
    
    def start_monitoring(self):
        """Start all monitoring"""
        self.system_monitor.start_monitoring()
        logger.info("Monitoring service started")
    
    def stop_monitoring(self):
        """Stop all monitoring"""
        self.system_monitor.stop_monitoring()
        logger.info("Monitoring service stopped")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall system health status"""
        system_metrics = self.system_monitor.get_current_metrics()
        request_stats = self.app_monitor.get_request_stats(hours=1)
        error_summary = self.app_monitor.get_error_summary(hours=1)
        
        issues = []
        
        if system_metrics.get("cpu_usage_percent", 0) > self.thresholds["cpu_usage_critical"]:
            issues.append("High CPU usage")
        
        if system_metrics.get("memory_usage_percent", 0) > self.thresholds["memory_usage_critical"]:
            issues.append("High memory usage")
        
        if system_metrics.get("disk_usage_percent", 0) > self.thresholds["disk_usage_critical"]:
            issues.append("High disk usage")
        
        # Check application metrics
        if isinstance(request_stats, dict) and "avg_response_time" in request_stats:
            if request_stats["avg_response_time"] > self.thresholds["response_time_slow"]:
                issues.append("Slow response times")
            
            if request_stats["error_rate"] > self.thresholds["error_rate_high"]:
                issues.append("High error rate")
        
        # Overall status
        if not issues:
            status = "healthy"
        elif len(issues) <= 2:
            status = "warning"
        else:
            status = "critical"
        
        return {
            "status": status,
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            "issues": issues,
            "system_metrics": system_metrics,
            "application_metrics": {
                "requests": request_stats,
                "errors": error_summary
            }
        }
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive monitoring statistics"""
        return {
            "service_info": {
                "start_time": self.start_time.isoformat(),
                "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
                "monitoring_active": self.system_monitor.monitoring
            },
            "system": {
                "current": self.system_monitor.get_current_metrics(),
                "history_1h": self.system_monitor.get_metrics_history(hours=1),
                "history_24h": self.system_monitor.get_metrics_history(hours=24)
            },
            "application": {
                "requests_1h": self.app_monitor.get_request_stats(hours=1),
                "requests_24h": self.app_monitor.get_request_stats(hours=24),
                "generation_1h": self.app_monitor.get_generation_stats(hours=1),
                "generation_24h": self.app_monitor.get_generation_stats(hours=24),
                "errors_1h": self.app_monitor.get_error_summary(hours=1),
                "errors_24h": self.app_monitor.get_error_summary(hours=24)
            },
            "thresholds": self.thresholds
        }
    
    def record_request(self, endpoint: str, method: str, duration: float, status_code: int, **kwargs):
        """Record request metrics"""
        self.app_monitor.record_request(endpoint, method, duration, status_code, **kwargs)
    
    def record_generation(self, event_type: str, duration: float = None, success: bool = True, **kwargs):
        """Record generation event"""
        self.app_monitor.record_generation_event(event_type, duration, success, kwargs)
    
    def record_error(self, error_type: str, endpoint: str = None, details: str = None):
        """Record error event"""
        self.app_monitor.record_error(error_type, endpoint, details)
    
    def update_threshold(self, threshold_name: str, value: float):
        """Update performance threshold"""
        if threshold_name in self.thresholds:
            self.thresholds[threshold_name] = value
            logger.info(f"Updated threshold {threshold_name} to {value}")
        else:
            logger.warning(f"Unknown threshold: {threshold_name}")

# Monitoring middleware for FastAPI
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class MonitoringMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for automatic request monitoring"""
    
    def __init__(self, app, monitoring_service: MonitoringService):
        super().__init__(app)
        self.monitoring_service = monitoring_service
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        try:
            response = await call_next(request)
            duration = time.time() - start_time
            
            # Record successful request
            self.monitoring_service.record_request(
                endpoint=request.url.path,
                method=request.method,
                duration=duration,
                status_code=response.status_code,
                user_id=getattr(request.state, 'user_id', None),
                session_id=getattr(request.state, 'session_id', None)
            )
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            
            # Record failed request
            self.monitoring_service.record_request(
                endpoint=request.url.path,
                method=request.method,
                duration=duration,
                status_code=500
            )
            
            # Record error
            self.monitoring_service.record_error(
                error_type=type(e).__name__,
                endpoint=request.url.path,
                details=str(e)[:500]  # Truncate long error messages
            )
            
            raise

# Performance decorator for monitoring function execution
def monitor_performance(operation_name: str, monitoring_service: MonitoringService = None):
    """Decorator to monitor function performance"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            error_details = None
            
            try:
                result = func(*args, **kwargs)
                return result
            
            except Exception as e:
                success = False
                error_details = str(e)
                raise
            
            finally:
                duration = time.time() - start_time
                
                if monitoring_service:
                    monitoring_service.record_generation(
                        event_type=operation_name,
                        duration=duration,
                        success=success,
                        function_name=func.__name__
                    )
                    
                    if not success and error_details:
                        monitoring_service.record_error(
                            error_type="function_error",
                            endpoint=f"function_{func.__name__}",
                            details=error_details
                        )
                
                logger.info(f"{operation_name} completed in {duration:.2f}s (success={success})")
        
        return wrapper
    return decorator
monitoring_service = MonitoringService()

class MonitoredOperation:
    """Context manager for monitoring operations"""
    
    def __init__(self, operation_name: str, monitoring_service: MonitoringService = None):
        self.operation_name = operation_name
        self.monitoring_service = monitoring_service or globals().get('monitoring_service')
        self.start_time = None
        self.success = True
        self.metadata = {}
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.success = exc_type is None
        
        if self.monitoring_service:
            self.monitoring_service.record_generation(
                event_type=self.operation_name,
                duration=duration,
                success=self.success,
                **self.metadata
            )
            
            if not self.success:
                self.monitoring_service.record_error(
                    error_type=exc_type.__name__ if exc_type else "unknown",
                    details=str(exc_val) if exc_val else ""
                )
    
    def add_metadata(self, **kwargs):
        """Add metadata to the operation"""
        self.metadata.update(kwargs)

def track_cache_performance(cache_name: str, hit: bool, operation_time: float = None):
    """Track cache performance metrics"""
    monitoring_service.record_generation(
        event_type=f"cache_{cache_name}",
        duration=operation_time,
        success=True,
        cache_hit=str(hit)
    )

def track_database_operation(operation: str, duration: float, success: bool = True):
    """Track database operation performance"""
    monitoring_service.record_generation(
        event_type=f"database_{operation}",
        duration=duration,
        success=success
    )

def track_embedding_generation(model_name: str, batch_size: int, duration: float, success: bool = True):
    """Track embedding generation performance"""
    monitoring_service.record_generation(
        event_type="embedding_generation",
        duration=duration,
        success=success,
        model=model_name,
        batch_size=str(batch_size)
    )