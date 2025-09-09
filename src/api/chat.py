"""Chat API endpoint for general chat functionality."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Chat request model."""
    message: str
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    session_id: str
    metadata: Optional[Dict[str, Any]] = None


@router.post("/")
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint.
    
    This endpoint handles general chat requests and can route to appropriate services.
    """
    try:
        logger.info(f"Chat request received: {request.message[:100]}...")
        
        # For now, return a simple echo response
        # In production, this would route to appropriate AI services
        response = ChatResponse(
            response=f"Received your message: {request.message}",
            session_id=request.session_id or "default-session",
            metadata={"status": "success"}
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def chat_health():
    """Check chat service health."""
    return {"status": "healthy", "service": "chat"}