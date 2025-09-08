"""Health check API endpoints."""

from fastapi import APIRouter, status
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
async def readiness_check() -> Dict[str, Any]:
    """Readiness check for all components.
    
    Returns:
        Readiness status for each component
    """
    ready_status = {
        "ready": True,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {},
    }
    
    # Check Vector DB
    try:
        vector_db = VectorDB()
        info = vector_db.get_collection_info()
        ready_status["checks"]["vector_db"] = {
            "status": "ready",
            "collection": info["name"],
            "points_count": info["points_count"],
        }
    except Exception as e:
        logger.error(f"Vector DB not ready: {e}")
        ready_status["checks"]["vector_db"] = {
            "status": "not_ready",
            "error": str(e),
        }
        ready_status["ready"] = False
    
    # Check Graph DB
    try:
        graph_db = GraphDB()
        with graph_db.driver.session() as session:
            result = session.run("RETURN 1 AS health")
            if result.single():
                ready_status["checks"]["graph_db"] = {
                    "status": "ready",
                    "database": settings.neo4j_database,
                }
            else:
                raise Exception("Graph DB health check failed")
    except Exception as e:
        logger.error(f"Graph DB not ready: {e}")
        ready_status["checks"]["graph_db"] = {
            "status": "not_ready",
            "error": str(e),
        }
        ready_status["ready"] = False
    finally:
        if 'graph_db' in locals():
            graph_db.close()
    
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
                "error": "OpenAI API key not set",
            }
            ready_status["ready"] = False
    except Exception as e:
        logger.error(f"Embedding service not ready: {e}")
        ready_status["checks"]["embedding_service"] = {
            "status": "not_ready",
            "error": str(e),
        }
        ready_status["ready"] = False
    
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