"""
Enhanced Error Handling and Retry Mechanisms for Legal Data APIs

This module provides comprehensive error handling, retry logic, circuit breakers,
and resilience patterns for the legal data integration system.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Callable, TypeVar, Generic
from enum import Enum
from dataclasses import dataclass, field
from functools import wraps
import structlog
import aiohttp
from aiohttp import ClientError, ClientTimeout, ClientResponseError
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential, 
    retry_if_exception_type,
    before_sleep_log,
    after_log
)
import asyncio_throttle

logger = structlog.get_logger()

T = TypeVar('T')


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification."""
    NETWORK = "network"
    API_ERROR = "api_error"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    DATA_PROCESSING = "data_processing"
    DATABASE = "database"
    VALIDATION = "validation"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"         # Blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class ErrorInfo:
    """Detailed error information."""
    error_type: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    timestamp: datetime
    service_name: Optional[str] = None
    endpoint: Optional[str] = None
    attempt_number: int = 1
    total_attempts: int = 1
    context: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None
    user_message: Optional[str] = None  # User-friendly error message
    recovery_suggestions: List[str] = field(default_factory=list)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on: List[type] = field(default_factory=lambda: [Exception])
    stop_on: List[type] = field(default_factory=list)


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout: float = 60.0
    half_open_max_calls: int = 3


class APIErrorClassifier:
    """Classifies API errors and determines appropriate handling."""
    
    @staticmethod
    def classify_error(error: Exception, context: Optional[Dict[str, Any]] = None) -> ErrorInfo:
        """Classify an error and return detailed information."""
        now = datetime.now(timezone.utc)
        context = context or {}
        
        if isinstance(error, aiohttp.ClientTimeout):
            return ErrorInfo(
                error_type="TimeoutError",
                category=ErrorCategory.TIMEOUT,
                severity=ErrorSeverity.MEDIUM,
                message=str(error),
                timestamp=now,
                context=context,
                user_message="The request timed out. Please try again.",
                recovery_suggestions=[
                    "Increase timeout value",
                    "Check network connectivity",
                    "Retry the request"
                ]
            )
        
        elif isinstance(error, aiohttp.ClientResponseError):
            if error.status == 429:
                return ErrorInfo(
                    error_type="RateLimitError",
                    category=ErrorCategory.RATE_LIMIT,
                    severity=ErrorSeverity.HIGH,
                    message=f"Rate limit exceeded: {error.message}",
                    timestamp=now,
                    context=context,
                    user_message="Too many requests. Please wait before retrying.",
                    recovery_suggestions=[
                        "Wait before retrying",
                        "Implement exponential backoff",
                        "Check API quota limits"
                    ]
                )
            elif error.status in [401, 403]:
                return ErrorInfo(
                    error_type="AuthenticationError",
                    category=ErrorCategory.AUTHENTICATION,
                    severity=ErrorSeverity.CRITICAL,
                    message=f"Authentication failed: {error.message}",
                    timestamp=now,
                    context=context,
                    user_message="Authentication failed. Please check your API credentials.",
                    recovery_suggestions=[
                        "Check API key validity",
                        "Verify authentication headers",
                        "Contact API provider if key is valid"
                    ]
                )
            elif error.status >= 500:
                return ErrorInfo(
                    error_type="ServerError",
                    category=ErrorCategory.API_ERROR,
                    severity=ErrorSeverity.HIGH,
                    message=f"Server error: {error.message}",
                    timestamp=now,
                    context=context,
                    user_message="The service is temporarily unavailable. Please try again later.",
                    recovery_suggestions=[
                        "Retry after exponential backoff",
                        "Check service status",
                        "Use fallback data source if available"
                    ]
                )
            else:
                return ErrorInfo(
                    error_type="ClientError",
                    category=ErrorCategory.API_ERROR,
                    severity=ErrorSeverity.MEDIUM,
                    message=f"Client error: {error.message}",
                    timestamp=now,
                    context=context,
                    user_message="There was an error with the request.",
                    recovery_suggestions=[
                        "Check request parameters",
                        "Validate input data",
                        "Review API documentation"
                    ]
                )
        
        elif isinstance(error, aiohttp.ClientConnectorError):
            return ErrorInfo(
                error_type="ConnectionError",
                category=ErrorCategory.NETWORK,
                severity=ErrorSeverity.HIGH,
                message=f"Connection failed: {error}",
                timestamp=now,
                context=context,
                user_message="Unable to connect to the service. Please check your internet connection.",
                recovery_suggestions=[
                    "Check internet connectivity",
                    "Verify service URL",
                    "Check for network firewalls"
                ]
            )
        
        elif isinstance(error, ValidationError):
            return ErrorInfo(
                error_type="ValidationError",
                category=ErrorCategory.VALIDATION,
                severity=ErrorSeverity.MEDIUM,
                message=str(error),
                timestamp=now,
                context=context,
                user_message="The provided data is invalid.",
                recovery_suggestions=[
                    "Check input data format",
                    "Validate required fields",
                    "Review data types"
                ]
            )
        
        else:
            return ErrorInfo(
                error_type=type(error).__name__,
                category=ErrorCategory.UNKNOWN,
                severity=ErrorSeverity.MEDIUM,
                message=str(error),
                timestamp=now,
                context=context,
                user_message="An unexpected error occurred.",
                recovery_suggestions=[
                    "Retry the operation",
                    "Check system logs",
                    "Contact support if error persists"
                ]
            )


class CircuitBreaker:
    """Circuit breaker pattern implementation for API calls."""
    
    def __init__(self, 
                 name: str, 
                 config: CircuitBreakerConfig,
                 error_classifier: Optional[APIErrorClassifier] = None):
        """Initialize circuit breaker."""
        self.name = name
        self.config = config
        self.error_classifier = error_classifier or APIErrorClassifier()
        
        # State tracking
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0
        
        # Statistics
        self.total_requests = 0
        self.total_failures = 0
        self.total_successes = 0
        self.state_transitions = []
        
        self.logger = logger.bind(circuit_breaker=name)
    
    async def call(self, func: Callable[[], T], *args, **kwargs) -> T:
        """Execute function through circuit breaker."""
        self.total_requests += 1
        
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._set_state(CircuitState.HALF_OPEN)
                self.half_open_calls = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN. Service unavailable."
                )
        
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.config.half_open_max_calls:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' max half-open calls exceeded."
                )
            self.half_open_calls += 1
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
            
        except Exception as e:
            self._on_failure(e)
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt to reset."""
        if self.last_failure_time is None:
            return False
        
        time_since_failure = time.time() - self.last_failure_time
        return time_since_failure >= self.config.timeout
    
    def _on_success(self):
        """Handle successful call."""
        self.total_successes += 1
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self._set_state(CircuitState.CLOSED)
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0
    
    def _on_failure(self, error: Exception):
        """Handle failed call."""
        self.total_failures += 1
        
        # Classify error to determine if it should trigger circuit breaker
        error_info = self.error_classifier.classify_error(error)
        
        # Only count certain types of errors for circuit breaking
        if error_info.category in [
            ErrorCategory.NETWORK, 
            ErrorCategory.TIMEOUT, 
            ErrorCategory.API_ERROR
        ] and error_info.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state in [CircuitState.CLOSED, CircuitState.HALF_OPEN]:
                if self.failure_count >= self.config.failure_threshold:
                    self._set_state(CircuitState.OPEN)
                    self.success_count = 0
    
    def _set_state(self, new_state: CircuitState):
        """Change circuit breaker state."""
        old_state = self.state
        self.state = new_state
        self.state_transitions.append({
            'from_state': old_state.value,
            'to_state': new_state.value,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'failure_count': self.failure_count,
            'success_count': self.success_count
        })
        
        self.logger.info(
            f"Circuit breaker state changed: {old_state.value} -> {new_state.value}",
            failure_count=self.failure_count,
            success_count=self.success_count
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            'name': self.name,
            'state': self.state.value,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'total_requests': self.total_requests,
            'total_failures': self.total_failures,
            'total_successes': self.total_successes,
            'failure_rate': self.total_failures / max(self.total_requests, 1),
            'last_failure_time': self.last_failure_time,
            'state_transitions': self.state_transitions[-10:],  # Last 10 transitions
            'config': {
                'failure_threshold': self.config.failure_threshold,
                'success_threshold': self.config.success_threshold,
                'timeout': self.config.timeout
            }
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class ValidationError(Exception):
    """Raised for data validation errors."""
    pass


class ResilientAPIClient:
    """API client with built-in resilience patterns."""
    
    def __init__(self, 
                 name: str,
                 base_url: str,
                 default_timeout: float = 30.0,
                 rate_limit_per_second: Optional[float] = None):
        """Initialize resilient API client."""
        self.name = name
        self.base_url = base_url
        self.default_timeout = default_timeout
        
        # Error handling
        self.error_classifier = APIErrorClassifier()
        
        # Circuit breaker
        circuit_config = CircuitBreakerConfig()
        self.circuit_breaker = CircuitBreaker(f"{name}_circuit", circuit_config)
        
        # Rate limiting
        self.rate_limiter = None
        if rate_limit_per_second:
            self.rate_limiter = asyncio_throttle.Throttler(rate_limit_per_second)
        
        # Request statistics
        self.request_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'retried_requests': 0,
            'avg_response_time': 0.0,
            'errors_by_category': {}
        }
        
        self.logger = logger.bind(api_client=name)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.INFO),
        after=after_log(logger, logging.INFO)
    )
    async def make_request(self,
                          method: str,
                          endpoint: str,
                          params: Optional[Dict[str, Any]] = None,
                          json_data: Optional[Dict[str, Any]] = None,
                          headers: Optional[Dict[str, str]] = None,
                          timeout: Optional[float] = None) -> Dict[str, Any]:
        """Make a resilient HTTP request."""
        
        # Apply rate limiting
        if self.rate_limiter:
            async with self.rate_limiter:
                return await self._execute_request(method, endpoint, params, json_data, headers, timeout)
        else:
            return await self._execute_request(method, endpoint, params, json_data, headers, timeout)
    
    async def _execute_request(self,
                              method: str,
                              endpoint: str,
                              params: Optional[Dict[str, Any]] = None,
                              json_data: Optional[Dict[str, Any]] = None,
                              headers: Optional[Dict[str, str]] = None,
                              timeout: Optional[float] = None) -> Dict[str, Any]:
        """Execute HTTP request through circuit breaker."""
        
        start_time = time.time()
        self.request_stats['total_requests'] += 1
        
        async def _make_http_call():
            url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
            request_timeout = ClientTimeout(total=timeout or self.default_timeout)
            
            async with aiohttp.ClientSession(timeout=request_timeout) as session:
                async with session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    headers=headers
                ) as response:
                    response.raise_for_status()
                    return await response.json()
        
        try:
            # Execute through circuit breaker
            result = await self.circuit_breaker.call(_make_http_call)
            
            # Update success statistics
            self.request_stats['successful_requests'] += 1
            response_time = time.time() - start_time
            self._update_avg_response_time(response_time)
            
            self.logger.info(
                f"Request successful: {method} {endpoint}",
                response_time=response_time,
                status="success"
            )
            
            return result
            
        except Exception as e:
            # Update failure statistics
            self.request_stats['failed_requests'] += 1
            error_info = self.error_classifier.classify_error(e, {
                'method': method,
                'endpoint': endpoint,
                'service': self.name
            })
            
            # Track error by category
            category = error_info.category.value
            self.request_stats['errors_by_category'][category] = \
                self.request_stats['errors_by_category'].get(category, 0) + 1
            
            self.logger.error(
                f"Request failed: {method} {endpoint}",
                error_type=error_info.error_type,
                category=error_info.category.value,
                severity=error_info.severity.value,
                message=error_info.message,
                user_message=error_info.user_message
            )
            
            # Re-raise with enhanced error information
            raise EnhancedAPIError(error_info) from e
    
    def _update_avg_response_time(self, response_time: float):
        """Update average response time using rolling average."""
        total_successful = self.request_stats['successful_requests']
        if total_successful == 1:
            self.request_stats['avg_response_time'] = response_time
        else:
            # Simple rolling average
            current_avg = self.request_stats['avg_response_time']
            self.request_stats['avg_response_time'] = \
                (current_avg * (total_successful - 1) + response_time) / total_successful
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of the API client."""
        circuit_stats = self.circuit_breaker.get_stats()
        
        # Determine health status
        if circuit_stats['state'] == 'open':
            health = 'unhealthy'
        elif circuit_stats['failure_rate'] > 0.1:  # More than 10% failure rate
            health = 'degraded'
        else:
            health = 'healthy'
        
        return {
            'service_name': self.name,
            'health_status': health,
            'circuit_breaker': circuit_stats,
            'request_stats': self.request_stats,
            'avg_response_time_ms': self.request_stats['avg_response_time'] * 1000,
            'last_check_time': datetime.now(timezone.utc).isoformat()
        }


class EnhancedAPIError(Exception):
    """Enhanced API error with detailed information."""
    
    def __init__(self, error_info: ErrorInfo):
        self.error_info = error_info
        super().__init__(error_info.message)
    
    def get_user_message(self) -> str:
        """Get user-friendly error message."""
        return self.error_info.user_message or "An error occurred"
    
    def get_recovery_suggestions(self) -> List[str]:
        """Get recovery suggestions."""
        return self.error_info.recovery_suggestions
    
    def is_retryable(self) -> bool:
        """Check if error is retryable."""
        return self.error_info.category not in [
            ErrorCategory.AUTHENTICATION,
            ErrorCategory.VALIDATION
        ]


class ErrorAggregator:
    """Aggregates and analyzes errors across the system."""
    
    def __init__(self):
        """Initialize error aggregator."""
        self.errors: List[ErrorInfo] = []
        self.max_errors = 1000  # Keep last 1000 errors
        self.logger = logger.bind(component="error_aggregator")
    
    def record_error(self, error_info: ErrorInfo):
        """Record an error for analysis."""
        self.errors.append(error_info)
        
        # Keep only recent errors
        if len(self.errors) > self.max_errors:
            self.errors = self.errors[-self.max_errors:]
        
        # Log error
        self.logger.error(
            "Error recorded",
            error_type=error_info.error_type,
            category=error_info.category.value,
            severity=error_info.severity.value,
            service=error_info.service_name,
            endpoint=error_info.endpoint
        )
    
    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get error summary for the specified time period."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent_errors = [e for e in self.errors if e.timestamp >= cutoff_time]
        
        if not recent_errors:
            return {
                'total_errors': 0,
                'time_period_hours': hours,
                'summary': "No errors in the specified time period"
            }
        
        # Group by category
        by_category = {}
        for error in recent_errors:
            category = error.category.value
            by_category[category] = by_category.get(category, 0) + 1
        
        # Group by severity
        by_severity = {}
        for error in recent_errors:
            severity = error.severity.value
            by_severity[severity] = by_severity.get(severity, 0) + 1
        
        # Group by service
        by_service = {}
        for error in recent_errors:
            service = error.service_name or 'unknown'
            by_service[service] = by_service.get(service, 0) + 1
        
        # Most common error types
        error_types = {}
        for error in recent_errors:
            error_type = error.error_type
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        return {
            'total_errors': len(recent_errors),
            'time_period_hours': hours,
            'by_category': by_category,
            'by_severity': by_severity,
            'by_service': by_service,
            'most_common_errors': sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:10],
            'critical_errors': len([e for e in recent_errors if e.severity == ErrorSeverity.CRITICAL]),
            'high_severity_errors': len([e for e in recent_errors if e.severity == ErrorSeverity.HIGH])
        }
    
    def get_recommendations(self) -> List[str]:
        """Get recommendations based on error patterns."""
        recommendations = []
        
        summary = self.get_error_summary()
        
        # Check for high error rates
        if summary['total_errors'] > 100:
            recommendations.append("High error rate detected. Consider implementing additional circuit breakers.")
        
        # Check for authentication issues
        if summary['by_category'].get('authentication', 0) > 5:
            recommendations.append("Multiple authentication errors. Check API key validity and rotation.")
        
        # Check for rate limiting issues
        if summary['by_category'].get('rate_limit', 0) > 10:
            recommendations.append("Rate limiting issues detected. Consider implementing adaptive throttling.")
        
        # Check for network issues
        if summary['by_category'].get('network', 0) > 20:
            recommendations.append("Network connectivity issues. Consider implementing fallback endpoints.")
        
        # Check for critical errors
        if summary.get('critical_errors', 0) > 0:
            recommendations.append("Critical errors detected. Immediate investigation required.")
        
        return recommendations


# Global error aggregator instance
error_aggregator = ErrorAggregator()


# Decorator for automatic error handling
def handle_errors(service_name: str = "unknown"):
    """Decorator to automatically handle and classify errors."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                error_info = APIErrorClassifier.classify_error(e, {
                    'function': func.__name__,
                    'service': service_name
                })
                error_info.service_name = service_name
                
                # Record error
                error_aggregator.record_error(error_info)
                
                # Re-raise as enhanced error
                raise EnhancedAPIError(error_info) from e
        return wrapper
    return decorator


# Example usage and testing
async def test_resilient_client():
    """Test the resilient API client."""
    
    # Create client
    client = ResilientAPIClient(
        name="test_api",
        base_url="https://httpbin.org",
        rate_limit_per_second=2.0
    )
    
    try:
        # Test successful request
        result = await client.make_request("GET", "/get", params={"test": "value"})
        print("Successful request:", result["args"])
        
        # Test error handling
        try:
            await client.make_request("GET", "/status/500")
        except EnhancedAPIError as e:
            print("Handled error:", e.get_user_message())
            print("Recovery suggestions:", e.get_recovery_suggestions())
        
        # Get health status
        health = client.get_health_status()
        print("Health status:", health['health_status'])
        
    except Exception as e:
        print("Unexpected error:", e)


if __name__ == "__main__":
    asyncio.run(test_resilient_client())