"""Main FastAPI application for Legal Analysis System."""

from fastapi import FastAPI, HTTPException, Depends, status, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import structlog
import uvicorn
from prometheus_client import make_asgi_app, Counter, Histogram
import time
import uuid

from .core.config import settings
from .api import retrieval, legal_analysis, health, metrics, smart_analysis, simple_analysis, case_management, mcp_endpoints, legal_data
# Temporarily comment out to fix nltk import error
# from .api.legal_data_websocket import websocket_endpoint
from .db.graph_db import GraphDB

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Metrics
request_count = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)
request_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"]
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Legal Analysis System", version="0.1.0")
    
    # Initialize database connections
    try:
        graph_db = GraphDB()
        logger.info("Database connections established")
    except Exception as e:
        logger.error(f"Failed to initialize databases: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Legal Analysis System")
    graph_db.close()


# Create FastAPI app
app = FastAPI(
    title="Legal Analysis System",
    description="Legal analysis system using GraphRAG and Vector search",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Custom exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# Middleware for request logging and metrics
@app.middleware("http")
async def log_requests(request, call_next):
    """Log all requests and collect metrics."""
    start_time = time.time()
    
    # Log request
    logger.info(
        "Request received",
        method=request.method,
        path=request.url.path,
        client=request.client.host if request.client else None,
    )
    
    # Process request
    response = await call_next(request)
    
    # Calculate duration
    duration = time.time() - start_time
    
    # Log response
    logger.info(
        "Request completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration=duration,
    )
    
    # Update metrics
    request_count.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
    ).inc()
    
    request_duration.labels(
        method=request.method,
        endpoint=request.url.path,
    ).observe(duration)
    
    return response


# Include routers
app.include_router(
    retrieval.router,
    prefix=f"{settings.api_prefix}/retrieval",
    tags=["retrieval"],
)

app.include_router(
    legal_analysis.router,
    prefix=f"{settings.api_prefix}/analysis",
    tags=["analysis"],
)

app.include_router(
    health.router,
    prefix=f"{settings.api_prefix}/health",
    tags=["health"],
)

app.include_router(
    metrics.router,
    prefix=f"{settings.api_prefix}/metrics",
    tags=["metrics"],
)

app.include_router(
    smart_analysis.router,
    prefix=f"{settings.api_prefix}/smart",
    tags=["smart"],
)

app.include_router(
    simple_analysis.router,
    prefix=f"{settings.api_prefix}/simple",
    tags=["simple"],
)

app.include_router(
    case_management.router,
    tags=["cases"],
)

app.include_router(
    mcp_endpoints.router,
    tags=["mcp"],
)

app.include_router(
    legal_data.router,
    tags=["legal-data"],
)


# WebSocket endpoints
# Temporarily comment out WebSocket endpoints due to nltk dependency
# @app.websocket("/ws/legal-data/{connection_id}")
# async def legal_data_websocket(websocket: WebSocket, connection_id: str):
#     """WebSocket endpoint for real-time legal data operations."""
#     await websocket_endpoint(websocket, connection_id)

# @app.websocket("/ws/legal-data")
# async def legal_data_websocket_auto(websocket: WebSocket):
#     """WebSocket endpoint with auto-generated connection ID."""
#     connection_id = str(uuid.uuid4())
#     await websocket_endpoint(websocket, connection_id)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
        "websocket_endpoints": {
            "legal_data": "/ws/legal-data/{connection_id}",
            "legal_data_auto": "/ws/legal-data"
        }
    }


# Mount Prometheus metrics endpoint
if settings.enable_metrics:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)


def run():
    """Run the application."""
    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()