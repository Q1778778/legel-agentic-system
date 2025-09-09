"""Main FastAPI application for Court Argument Simulator."""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import structlog
import uvicorn
from prometheus_client import make_asgi_app, Counter, Histogram
import time

from .core.config import settings
from .api import retrieval, health, metrics, agents, workflows, websocket, legal_workflow, legal_analysis, legacy_redirect
from .db.graph_db import GraphDB
from .db.vector_db import VectorDB

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
    """Application lifespan manager with graceful database handling."""
    # Startup
    logger.info("Starting Legal Analysis System", version="2.0.0")
    
    # Initialize database connections with graceful degradation
    graph_db = None
    vector_db = None
    
    # Try to connect to Neo4j
    try:
        graph_db = GraphDB()
        if graph_db.is_available():
            logger.info("Neo4j graph database connected successfully")
            app.state.graph_db = graph_db
        else:
            logger.warning("Neo4j not available - graph features will be limited")
            app.state.graph_db = None
    except Exception as e:
        logger.error(f"Failed to initialize Neo4j: {e}")
        app.state.graph_db = None
    
    # Try to connect to Qdrant
    try:
        vector_db = VectorDB()
        if vector_db.is_available():
            logger.info("Qdrant vector database connected successfully")
            app.state.vector_db = vector_db
        else:
            logger.warning("Qdrant not available - vector search will be limited")
            app.state.vector_db = None
    except Exception as e:
        logger.error(f"Failed to initialize Qdrant: {e}")
        app.state.vector_db = None
    
    # Warn if both databases are unavailable
    if not app.state.graph_db and not app.state.vector_db:
        logger.error("WARNING: Both databases unavailable - system running in severely degraded mode")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Legal Analysis System")
    if graph_db:
        graph_db.close()
    # Qdrant client doesn't need explicit closing


# Create FastAPI app
app = FastAPI(
    title="Legal Analysis System",
    description="AI-powered legal argument analysis and debate system with GraphRAG",
    version="2.0.0",
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


# Include routers - Core functionality
app.include_router(
    retrieval.router,
    prefix=f"{settings.api_prefix}/retrieval",
    tags=["retrieval"],
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

# New legal workflow endpoints (replacing simulation)
app.include_router(
    legal_workflow.router,
    prefix=f"{settings.api_prefix}/legal",
    tags=["legal-workflow"],
)

app.include_router(
    legal_analysis.router,
    prefix=f"{settings.api_prefix}/analysis",
    tags=["legal-analysis"],
)

app.include_router(
    agents.router,
    prefix=f"{settings.api_prefix}/agents",
    tags=["agents"],
)

# Include workflow and websocket routers
app.include_router(workflows.router)
app.include_router(websocket.router)

# Legacy endpoints for backward compatibility (will redirect to new system)
app.include_router(
    legacy_redirect.router,
    prefix=f"{settings.api_prefix}/simulation",
    tags=["legacy-simulation"],
)

app.include_router(
    legacy_redirect.router,
    prefix=f"{settings.api_prefix}/smart",
    tags=["legacy-smart"],
)

app.include_router(
    legacy_redirect.router,
    prefix=f"{settings.api_prefix}/simple",
    tags=["legacy-simple"],
)


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