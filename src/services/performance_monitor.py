"""
Performance Monitoring and Analytics for Legal Data Integration System

This module provides comprehensive performance monitoring, metrics collection,
alerting, and analytics for the legal data API integration system.
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import statistics
import structlog
import psutil
import aiofiles
import json
from contextlib import asynccontextmanager

from .error_handling import error_aggregator

logger = structlog.get_logger()


class MetricType(Enum):
    """Types of metrics."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class MetricValue:
    """Single metric value with timestamp."""
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class PerformanceThresholds:
    """Performance thresholds for monitoring."""
    response_time_ms_warning: float = 2000.0
    response_time_ms_critical: float = 5000.0
    error_rate_warning: float = 0.05  # 5%
    error_rate_critical: float = 0.10  # 10%
    memory_usage_warning: float = 0.80  # 80%
    memory_usage_critical: float = 0.90  # 90%
    cpu_usage_warning: float = 0.80  # 80%
    cpu_usage_critical: float = 0.90  # 90%
    disk_usage_warning: float = 0.85  # 85%
    disk_usage_critical: float = 0.95  # 95%
    api_quota_warning: float = 0.80  # 80% of quota
    api_quota_critical: float = 0.95  # 95% of quota


@dataclass
class Alert:
    """System alert."""
    id: str
    metric_name: str
    severity: AlertSeverity
    message: str
    current_value: float
    threshold_value: float
    timestamp: datetime
    resolved: bool = False
    resolved_timestamp: Optional[datetime] = None
    tags: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """Collects and stores performance metrics."""
    
    def __init__(self, max_datapoints: int = 1000):
        """Initialize metrics collector."""
        self.max_datapoints = max_datapoints
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_datapoints))
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = defaultdict(float)
        self.logger = logger.bind(component="metrics_collector")
    
    def record_counter(self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None):
        """Record counter metric."""
        self.counters[name] += value
        self._record_metric(name, value, MetricType.COUNTER, tags)
    
    def record_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Record gauge metric."""
        self.gauges[name] = value
        self._record_metric(name, value, MetricType.GAUGE, tags)
    
    def record_histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Record histogram metric."""
        self._record_metric(name, value, MetricType.HISTOGRAM, tags)
    
    def _record_metric(self, name: str, value: float, metric_type: MetricType, tags: Optional[Dict[str, str]]):
        """Internal method to record metric."""
        metric_value = MetricValue(
            value=value,
            timestamp=datetime.now(timezone.utc),
            tags=tags or {}
        )
        
        metric_key = f"{name}:{metric_type.value}"
        self.metrics[metric_key].append(metric_value)
        
        self.logger.debug(
            f"Recorded {metric_type.value} metric",
            metric_name=name,
            value=value,
            tags=tags
        )
    
    def get_metric_stats(self, name: str, metric_type: MetricType, hours: int = 1) -> Optional[Dict[str, Any]]:
        """Get statistics for a metric over time period."""
        metric_key = f"{name}:{metric_type.value}"
        
        if metric_key not in self.metrics:
            return None
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent_values = [
            mv.value for mv in self.metrics[metric_key]
            if mv.timestamp >= cutoff_time
        ]
        
        if not recent_values:
            return None
        
        return {
            'count': len(recent_values),
            'min': min(recent_values),
            'max': max(recent_values),
            'mean': statistics.mean(recent_values),
            'median': statistics.median(recent_values),
            'stddev': statistics.stdev(recent_values) if len(recent_values) > 1 else 0.0,
            'sum': sum(recent_values),
            'p95': self._percentile(recent_values, 0.95),
            'p99': self._percentile(recent_values, 0.99)
        }
    
    def _percentile(self, values: List[float], p: float) -> float:
        """Calculate percentile."""
        sorted_values = sorted(values)
        index = int(len(sorted_values) * p)
        return sorted_values[min(index, len(sorted_values) - 1)]
    
    def get_all_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics."""
        summary = {
            'counters': dict(self.counters),
            'gauges': dict(self.gauges),
            'total_datapoints': sum(len(deque_obj) for deque_obj in self.metrics.values()),
            'metric_names': list(set(name.split(':')[0] for name in self.metrics.keys())),
            'collection_time': datetime.now(timezone.utc).isoformat()
        }
        
        return summary


class SystemMonitor:
    """Monitors system resource usage."""
    
    def __init__(self, metrics_collector: MetricsCollector):
        """Initialize system monitor."""
        self.metrics = metrics_collector
        self.logger = logger.bind(component="system_monitor")
        self._monitoring = False
        self._monitor_task = None
    
    async def start_monitoring(self, interval: float = 30.0):
        """Start system monitoring."""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval))
        self.logger.info(f"Started system monitoring with {interval}s interval")
    
    async def stop_monitoring(self):
        """Stop system monitoring."""
        self._monitoring = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Stopped system monitoring")
    
    async def _monitor_loop(self, interval: float):
        """Main monitoring loop."""
        while self._monitoring:
            try:
                await self._collect_system_metrics()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(interval)
    
    async def _collect_system_metrics(self):
        """Collect system metrics."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.metrics.record_gauge("system.cpu_usage_percent", cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.metrics.record_gauge("system.memory_usage_percent", memory.percent)
            self.metrics.record_gauge("system.memory_used_bytes", memory.used)
            self.metrics.record_gauge("system.memory_available_bytes", memory.available)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            self.metrics.record_gauge("system.disk_usage_percent", disk_percent)
            self.metrics.record_gauge("system.disk_used_bytes", disk.used)
            self.metrics.record_gauge("system.disk_free_bytes", disk.free)
            
            # Network I/O
            network = psutil.net_io_counters()
            self.metrics.record_counter("system.network_bytes_sent", network.bytes_sent)
            self.metrics.record_counter("system.network_bytes_recv", network.bytes_recv)
            
            # Process info
            process = psutil.Process()
            self.metrics.record_gauge("process.cpu_percent", process.cpu_percent())
            self.metrics.record_gauge("process.memory_percent", process.memory_percent())
            self.metrics.record_gauge("process.num_threads", process.num_threads())
            
            # File descriptors (Unix only)
            try:
                self.metrics.record_gauge("process.num_fds", process.num_fds())
            except (AttributeError, OSError):
                pass  # Not available on all platforms
            
        except Exception as e:
            self.logger.error(f"Error collecting system metrics: {e}")


class APIMonitor:
    """Monitors API performance and usage."""
    
    def __init__(self, metrics_collector: MetricsCollector):
        """Initialize API monitor."""
        self.metrics = metrics_collector
        self.api_quotas: Dict[str, Dict[str, Any]] = {}
        self.logger = logger.bind(component="api_monitor")
    
    def record_api_request(self, 
                          api_name: str, 
                          endpoint: str, 
                          status_code: int, 
                          response_time_ms: float,
                          request_size_bytes: Optional[int] = None,
                          response_size_bytes: Optional[int] = None):
        """Record API request metrics."""
        tags = {
            'api': api_name,
            'endpoint': endpoint,
            'status': str(status_code)
        }
        
        # Request count
        self.metrics.record_counter("api.requests_total", 1.0, tags)
        
        # Response time
        self.metrics.record_histogram("api.response_time_ms", response_time_ms, tags)
        
        # Error tracking
        if status_code >= 400:
            self.metrics.record_counter("api.errors_total", 1.0, tags)
        
        # Data transfer
        if request_size_bytes:
            self.metrics.record_histogram("api.request_size_bytes", request_size_bytes, tags)
        
        if response_size_bytes:
            self.metrics.record_histogram("api.response_size_bytes", response_size_bytes, tags)
    
    def record_api_quota_usage(self, api_name: str, used: int, limit: int, window: str):
        """Record API quota usage."""
        usage_percent = (used / limit) * 100 if limit > 0 else 0
        
        self.api_quotas[api_name] = {
            'used': used,
            'limit': limit,
            'usage_percent': usage_percent,
            'window': window,
            'timestamp': datetime.now(timezone.utc)
        }
        
        tags = {'api': api_name, 'window': window}
        self.metrics.record_gauge("api.quota_usage_percent", usage_percent, tags)
        self.metrics.record_gauge("api.quota_used", used, tags)
        self.metrics.record_gauge("api.quota_limit", limit, tags)
    
    def get_api_health(self, api_name: str, hours: int = 1) -> Dict[str, Any]:
        """Get API health status."""
        # Response time stats
        response_time_stats = self.metrics.get_metric_stats(
            "api.response_time_ms", 
            MetricType.HISTOGRAM, 
            hours
        )
        
        # Error rate calculation
        total_requests = 0
        error_requests = 0
        
        # Get request counts by status
        for metric_key, values in self.metrics.metrics.items():
            if metric_key.startswith("api.requests_total:counter"):
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
                recent_values = [mv for mv in values if mv.timestamp >= cutoff_time]
                
                for mv in recent_values:
                    if mv.tags.get('api') == api_name:
                        total_requests += mv.value
                        if int(mv.tags.get('status', 200)) >= 400:
                            error_requests += mv.value
        
        error_rate = error_requests / total_requests if total_requests > 0 else 0.0
        
        # Quota status
        quota_info = self.api_quotas.get(api_name, {})
        
        # Determine health status
        health_status = "healthy"
        issues = []
        
        if response_time_stats and response_time_stats['p95'] > 5000:
            health_status = "degraded"
            issues.append("High response times")
        
        if error_rate > 0.1:
            health_status = "unhealthy"
            issues.append("High error rate")
        
        if quota_info.get('usage_percent', 0) > 90:
            health_status = "degraded"
            issues.append("High quota usage")
        
        return {
            'api_name': api_name,
            'health_status': health_status,
            'issues': issues,
            'response_time_stats': response_time_stats,
            'error_rate': error_rate,
            'total_requests': total_requests,
            'quota_info': quota_info,
            'evaluation_period_hours': hours
        }


class AlertManager:
    """Manages alerts and notifications."""
    
    def __init__(self, 
                 metrics_collector: MetricsCollector,
                 thresholds: Optional[PerformanceThresholds] = None):
        """Initialize alert manager."""
        self.metrics = metrics_collector
        self.thresholds = thresholds or PerformanceThresholds()
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self.max_history = 1000
        self.logger = logger.bind(component="alert_manager")
    
    async def check_all_alerts(self):
        """Check all metrics against thresholds and generate alerts."""
        # System resource alerts
        await self._check_system_alerts()
        
        # API performance alerts
        await self._check_api_alerts()
        
        # Error rate alerts
        await self._check_error_alerts()
    
    async def _check_system_alerts(self):
        """Check system resource alerts."""
        # CPU usage
        cpu_stats = self.metrics.get_metric_stats("system.cpu_usage_percent", MetricType.GAUGE, 1)
        if cpu_stats:
            await self._check_threshold_alert(
                "system.cpu_usage",
                cpu_stats['mean'],
                self.thresholds.cpu_usage_warning * 100,
                self.thresholds.cpu_usage_critical * 100,
                "CPU usage is high",
                "percent"
            )
        
        # Memory usage
        memory_stats = self.metrics.get_metric_stats("system.memory_usage_percent", MetricType.GAUGE, 1)
        if memory_stats:
            await self._check_threshold_alert(
                "system.memory_usage",
                memory_stats['mean'],
                self.thresholds.memory_usage_warning * 100,
                self.thresholds.memory_usage_critical * 100,
                "Memory usage is high",
                "percent"
            )
        
        # Disk usage
        disk_stats = self.metrics.get_metric_stats("system.disk_usage_percent", MetricType.GAUGE, 1)
        if disk_stats:
            await self._check_threshold_alert(
                "system.disk_usage",
                disk_stats['mean'],
                self.thresholds.disk_usage_warning * 100,
                self.thresholds.disk_usage_critical * 100,
                "Disk usage is high",
                "percent"
            )
    
    async def _check_api_alerts(self):
        """Check API performance alerts."""
        # Response time alerts
        response_time_stats = self.metrics.get_metric_stats("api.response_time_ms", MetricType.HISTOGRAM, 1)
        if response_time_stats:
            await self._check_threshold_alert(
                "api.response_time",
                response_time_stats['p95'],
                self.thresholds.response_time_ms_warning,
                self.thresholds.response_time_ms_critical,
                "API response time is high",
                "milliseconds"
            )
    
    async def _check_error_alerts(self):
        """Check error rate alerts."""
        error_summary = error_aggregator.get_error_summary(1)
        
        if error_summary['total_errors'] > 0:
            # Calculate error rate (simplified)
            error_rate = min(error_summary['total_errors'] / 100, 1.0)  # Assume 100 total operations
            
            await self._check_threshold_alert(
                "system.error_rate",
                error_rate,
                self.thresholds.error_rate_warning,
                self.thresholds.error_rate_critical,
                "System error rate is high",
                "ratio"
            )
    
    async def _check_threshold_alert(self, 
                                   metric_name: str, 
                                   current_value: float,
                                   warning_threshold: float, 
                                   critical_threshold: float,
                                   message_template: str,
                                   unit: str):
        """Check threshold and create/resolve alerts."""
        alert_id = f"threshold_{metric_name}"
        
        # Determine severity
        severity = None
        if current_value >= critical_threshold:
            severity = AlertSeverity.CRITICAL
        elif current_value >= warning_threshold:
            severity = AlertSeverity.WARNING
        
        # Create or update alert
        if severity:
            threshold_value = critical_threshold if severity == AlertSeverity.CRITICAL else warning_threshold
            
            if alert_id in self.active_alerts:
                # Update existing alert
                alert = self.active_alerts[alert_id]
                alert.current_value = current_value
                alert.timestamp = datetime.now(timezone.utc)
                
                # Check if severity changed
                if alert.severity != severity:
                    alert.severity = severity
                    alert.threshold_value = threshold_value
                    self.logger.warning(
                        f"Alert severity changed: {metric_name}",
                        old_severity=alert.severity.value,
                        new_severity=severity.value,
                        current_value=current_value
                    )
            else:
                # Create new alert
                alert = Alert(
                    id=alert_id,
                    metric_name=metric_name,
                    severity=severity,
                    message=f"{message_template}: {current_value:.2f} {unit}",
                    current_value=current_value,
                    threshold_value=threshold_value,
                    timestamp=datetime.now(timezone.utc)
                )
                
                self.active_alerts[alert_id] = alert
                self.alert_history.append(alert)
                
                self.logger.error(
                    f"New alert: {metric_name}",
                    severity=severity.value,
                    current_value=current_value,
                    threshold=threshold_value,
                    message=alert.message
                )
        
        else:
            # Resolve alert if it exists
            if alert_id in self.active_alerts:
                alert = self.active_alerts[alert_id]
                alert.resolved = True
                alert.resolved_timestamp = datetime.now(timezone.utc)
                
                del self.active_alerts[alert_id]
                
                self.logger.info(
                    f"Alert resolved: {metric_name}",
                    current_value=current_value,
                    message=alert.message
                )
        
        # Cleanup old history
        if len(self.alert_history) > self.max_history:
            self.alert_history = self.alert_history[-self.max_history:]
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts."""
        return [
            {
                'id': alert.id,
                'metric_name': alert.metric_name,
                'severity': alert.severity.value,
                'message': alert.message,
                'current_value': alert.current_value,
                'threshold_value': alert.threshold_value,
                'timestamp': alert.timestamp.isoformat(),
                'duration_seconds': (datetime.now(timezone.utc) - alert.timestamp).total_seconds()
            }
            for alert in self.active_alerts.values()
        ]
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get alert summary."""
        active_by_severity = defaultdict(int)
        for alert in self.active_alerts.values():
            active_by_severity[alert.severity.value] += 1
        
        return {
            'total_active_alerts': len(self.active_alerts),
            'active_by_severity': dict(active_by_severity),
            'total_historical_alerts': len(self.alert_history),
            'last_check_time': datetime.now(timezone.utc).isoformat()
        }


class PerformanceAnalyzer:
    """Analyzes performance trends and provides insights."""
    
    def __init__(self, metrics_collector: MetricsCollector):
        """Initialize performance analyzer."""
        self.metrics = metrics_collector
        self.logger = logger.bind(component="performance_analyzer")
    
    def analyze_trends(self, hours: int = 24) -> Dict[str, Any]:
        """Analyze performance trends over time."""
        analysis = {
            'analysis_period_hours': hours,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'system_performance': self._analyze_system_performance(hours),
            'api_performance': self._analyze_api_performance(hours),
            'error_analysis': self._analyze_errors(hours),
            'recommendations': []
        }
        
        # Generate recommendations
        analysis['recommendations'] = self._generate_recommendations(analysis)
        
        return analysis
    
    def _analyze_system_performance(self, hours: int) -> Dict[str, Any]:
        """Analyze system performance metrics."""
        cpu_stats = self.metrics.get_metric_stats("system.cpu_usage_percent", MetricType.GAUGE, hours)
        memory_stats = self.metrics.get_metric_stats("system.memory_usage_percent", MetricType.GAUGE, hours)
        
        return {
            'cpu_usage': cpu_stats,
            'memory_usage': memory_stats,
            'status': 'healthy' if (
                (not cpu_stats or cpu_stats['mean'] < 80) and 
                (not memory_stats or memory_stats['mean'] < 80)
            ) else 'degraded'
        }
    
    def _analyze_api_performance(self, hours: int) -> Dict[str, Any]:
        """Analyze API performance metrics."""
        response_time_stats = self.metrics.get_metric_stats("api.response_time_ms", MetricType.HISTOGRAM, hours)
        
        return {
            'response_times': response_time_stats,
            'status': 'healthy' if (
                not response_time_stats or response_time_stats['p95'] < 2000
            ) else 'degraded'
        }
    
    def _analyze_errors(self, hours: int) -> Dict[str, Any]:
        """Analyze error patterns."""
        error_summary = error_aggregator.get_error_summary(hours)
        
        return {
            'error_summary': error_summary,
            'status': 'healthy' if error_summary['total_errors'] < 10 else 'degraded'
        }
    
    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate performance recommendations."""
        recommendations = []
        
        # System recommendations
        sys_perf = analysis['system_performance']
        if sys_perf['cpu_usage'] and sys_perf['cpu_usage']['mean'] > 80:
            recommendations.append("High CPU usage detected. Consider scaling horizontally or optimizing CPU-intensive operations.")
        
        if sys_perf['memory_usage'] and sys_perf['memory_usage']['mean'] > 80:
            recommendations.append("High memory usage detected. Consider implementing memory pooling or garbage collection tuning.")
        
        # API recommendations
        api_perf = analysis['api_performance']
        if api_perf['response_times'] and api_perf['response_times']['p95'] > 2000:
            recommendations.append("High API response times detected. Consider implementing caching or optimizing database queries.")
        
        # Error recommendations
        error_analysis = analysis['error_analysis']
        if error_analysis['error_summary']['total_errors'] > 50:
            recommendations.append("High error rate detected. Review error logs and implement additional error handling.")
        
        # Add error aggregator recommendations
        recommendations.extend(error_aggregator.get_recommendations())
        
        return recommendations


class PerformanceReporter:
    """Generates performance reports."""
    
    def __init__(self, 
                 metrics_collector: MetricsCollector,
                 alert_manager: AlertManager,
                 analyzer: PerformanceAnalyzer):
        """Initialize performance reporter."""
        self.metrics = metrics_collector
        self.alert_manager = alert_manager
        self.analyzer = analyzer
        self.logger = logger.bind(component="performance_reporter")
    
    async def generate_report(self, hours: int = 24) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        report = {
            'report_type': 'performance_summary',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'period_hours': hours,
            'metrics_summary': self.metrics.get_all_metrics_summary(),
            'alert_summary': self.alert_manager.get_alert_summary(),
            'active_alerts': self.alert_manager.get_active_alerts(),
            'performance_analysis': self.analyzer.analyze_trends(hours),
            'system_info': await self._get_system_info()
        }
        
        return report
    
    async def _get_system_info(self) -> Dict[str, Any]:
        """Get system information."""
        try:
            return {
                'python_version': psutil.PYTHON,
                'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat(),
                'cpu_count': psutil.cpu_count(),
                'memory_total_gb': psutil.virtual_memory().total / (1024**3),
                'disk_total_gb': psutil.disk_usage('/').total / (1024**3)
            }
        except Exception as e:
            self.logger.error(f"Error getting system info: {e}")
            return {}
    
    async def save_report(self, report: Dict[str, Any], filepath: str):
        """Save report to file."""
        try:
            async with aiofiles.open(filepath, 'w') as f:
                await f.write(json.dumps(report, indent=2, default=str))
            
            self.logger.info(f"Performance report saved to {filepath}")
        except Exception as e:
            self.logger.error(f"Error saving report: {e}")


@asynccontextmanager
async def performance_timer(metrics_collector: MetricsCollector, 
                          metric_name: str,
                          tags: Optional[Dict[str, str]] = None):
    """Context manager for timing operations."""
    start_time = time.time()
    try:
        yield
    finally:
        duration_ms = (time.time() - start_time) * 1000
        metrics_collector.record_histogram(metric_name, duration_ms, tags)


class PerformanceMonitor:
    """Main performance monitoring system."""
    
    def __init__(self, 
                 thresholds: Optional[PerformanceThresholds] = None,
                 monitor_interval: float = 30.0):
        """Initialize performance monitor."""
        self.thresholds = thresholds or PerformanceThresholds()
        self.monitor_interval = monitor_interval
        
        # Components
        self.metrics = MetricsCollector()
        self.system_monitor = SystemMonitor(self.metrics)
        self.api_monitor = APIMonitor(self.metrics)
        self.alert_manager = AlertManager(self.metrics, self.thresholds)
        self.analyzer = PerformanceAnalyzer(self.metrics)
        self.reporter = PerformanceReporter(self.metrics, self.alert_manager, self.analyzer)
        
        self.logger = logger.bind(component="performance_monitor")
        self._running = False
        self._monitor_task = None
    
    async def start(self):
        """Start performance monitoring."""
        if self._running:
            return
        
        self._running = True
        
        # Start system monitoring
        await self.system_monitor.start_monitoring(self.monitor_interval)
        
        # Start alert checking
        self._monitor_task = asyncio.create_task(self._alert_check_loop())
        
        self.logger.info("Performance monitoring started")
    
    async def stop(self):
        """Stop performance monitoring."""
        self._running = False
        
        # Stop system monitoring
        await self.system_monitor.stop_monitoring()
        
        # Stop alert checking
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Performance monitoring stopped")
    
    async def _alert_check_loop(self):
        """Alert checking loop."""
        while self._running:
            try:
                await self.alert_manager.check_all_alerts()
                await asyncio.sleep(self.monitor_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in alert check loop: {e}")
                await asyncio.sleep(self.monitor_interval)
    
    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for performance dashboard."""
        return {
            'metrics_summary': self.metrics.get_all_metrics_summary(),
            'alert_summary': self.alert_manager.get_alert_summary(),
            'active_alerts': self.alert_manager.get_active_alerts(),
            'system_health': {
                'cpu': self.metrics.get_metric_stats("system.cpu_usage_percent", MetricType.GAUGE, 1),
                'memory': self.metrics.get_metric_stats("system.memory_usage_percent", MetricType.GAUGE, 1),
                'disk': self.metrics.get_metric_stats("system.disk_usage_percent", MetricType.GAUGE, 1)
            },
            'api_health': {
                'response_time': self.metrics.get_metric_stats("api.response_time_ms", MetricType.HISTOGRAM, 1),
                'request_count': self.metrics.counters.get('api.requests_total', 0),
                'error_count': self.metrics.counters.get('api.errors_total', 0)
            }
        }


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


# Example usage and testing
async def test_performance_monitor():
    """Test the performance monitoring system."""
    
    # Start monitoring
    await performance_monitor.start()
    
    try:
        # Simulate some API calls
        for i in range(10):
            async with performance_timer(
                performance_monitor.metrics, 
                "test.operation_time_ms",
                {'operation': 'test_call'}
            ):
                await asyncio.sleep(0.1)  # Simulate work
            
            # Record API metrics
            performance_monitor.api_monitor.record_api_request(
                api_name="test_api",
                endpoint="/test",
                status_code=200 if i < 8 else 500,
                response_time_ms=100 + i * 10
            )
        
        # Wait for monitoring to collect data
        await asyncio.sleep(35)
        
        # Generate report
        report = await performance_monitor.reporter.generate_report(hours=1)
        
        print("Performance Report:")
        print(f"Total requests: {report['metrics_summary']['counters']}")
        print(f"Active alerts: {len(report['active_alerts'])}")
        print(f"Recommendations: {len(report['performance_analysis']['recommendations'])}")
        
    finally:
        await performance_monitor.stop()


if __name__ == "__main__":
    asyncio.run(test_performance_monitor())