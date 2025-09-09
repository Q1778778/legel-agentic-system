"""Health check API endpoints."""

from fastapi import APIRouter, status, Request
from typing import Dict, Any
import structlog
from datetime import datetime

from ..db.vector_db import VectorDB
from ..db.graph_db import GraphDB
from ..core.config import settings

logger = structlog.get_logger()
router = APIRouter()


@router.get(
    "/",
    summary="Health check",
    description="Basic health check endpoint",
)
async def health_check() -> Dict[str, str]:
    """Basic health check.
    
    Returns:
        Health status
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.app_name,
        "version": "0.1.0",
    }


@router.get(
    "/ready",
    summary="Readiness check",
    description="Check if service is ready to handle requests",
)
async def readiness_check(request: Request) -> Dict[str, Any]:
    """Readiness check for all components.
    
    Returns:
        Readiness status for each component
    """
    ready_status = {
        "ready": True,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {},
        "degraded_mode": False,
    }
    
    # Check Vector DB using app state if available
    try:
        vector_db = getattr(request.app.state, 'vector_db', None)
        if vector_db and vector_db.is_available():
            info = vector_db.get_collection_info()
            ready_status["checks"]["vector_db"] = {
                "status": "ready",
                "collection": info.get("name", "unknown"),
                "points_count": info.get("points_count", 0),
            }
        else:
            ready_status["checks"]["vector_db"] = {
                "status": "degraded",
                "message": "Vector database not available - running without vector search",
            }
            ready_status["degraded_mode"] = True
    except Exception as e:
        logger.error(f"Vector DB check failed: {e}")
        ready_status["checks"]["vector_db"] = {
            "status": "error",
            "error": str(e),
        }
        ready_status["degraded_mode"] = True
    
    # Check Graph DB using app state if available
    try:
        graph_db = getattr(request.app.state, 'graph_db', None)
        if graph_db and graph_db.is_available():
            ready_status["checks"]["graph_db"] = {
                "status": "ready",
                "database": settings.neo4j_database,
                "uri": settings.neo4j_uri,
            }
        else:
            ready_status["checks"]["graph_db"] = {
                "status": "degraded",
                "message": "Graph database not available - running without graph features",
            }
            ready_status["degraded_mode"] = True
    except Exception as e:
        logger.error(f"Graph DB check failed: {e}")
        ready_status["checks"]["graph_db"] = {
            "status": "error",
            "error": str(e),
        }
        ready_status["degraded_mode"] = True
    
    # Check embedding service
    try:
        if settings.openai_api_key:
            ready_status["checks"]["embedding_service"] = {
                "status": "ready",
                "model": settings.embedding_model,
            }
        else:
            ready_status["checks"]["embedding_service"] = {
                "status": "not_configured",
                "message": "OpenAI API key not set - embeddings unavailable",
            }
            ready_status["degraded_mode"] = True
    except Exception as e:
        logger.error(f"Embedding service check failed: {e}")
        ready_status["checks"]["embedding_service"] = {
            "status": "error",
            "error": str(e),
        }
        ready_status["degraded_mode"] = True
    
    # Determine overall readiness
    # System is ready if at least one database is available
    vector_ok = ready_status["checks"].get("vector_db", {}).get("status") == "ready"
    graph_ok = ready_status["checks"].get("graph_db", {}).get("status") == "ready"
    
    if not vector_ok and not graph_ok:
        ready_status["ready"] = False
        ready_status["message"] = "System not ready - all databases unavailable"
    elif ready_status["degraded_mode"]:
        ready_status["message"] = "System ready but running in degraded mode"
    else:
        ready_status["message"] = "System fully operational"
    
    return ready_status


@router.get(
    "/live",
    summary="Liveness check",
    description="Check if service is alive",
)
async def liveness_check() -> Dict[str, str]:
    """Liveness check.
    
    Returns:
        Liveness status
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
    }