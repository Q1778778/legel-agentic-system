"""
MCP API Endpoints
REST API endpoints for MCP server integration.
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Dict, Any, Optional, List
import json
import asyncio
from pydantic import BaseModel, Field

import structlog

from ..services.mcp_sdk_bridge import get_mcp_bridge
from ..services.mcp_session_manager import get_session_manager
from ..services.mcp_initializer import get_mcp_initializer

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/mcp")


# Request/Response Models
class ExtractChatRequest(BaseModel):
    """Chat extraction request model."""
    session_id: Optional[str] = None
    user_input: str
    context: Optional[Dict[str, Any]] = None


class ExtractFileRequest(BaseModel):
    """File extraction request model."""
    file_content: Optional[str] = None
    file_path: Optional[str] = None
    file_type: str = "auto"


class ConsultationInitRequest(BaseModel):
    """Consultation initialization request."""
    case_data: Dict[str, Any]
    session_id: Optional[str] = None


class ConsultationMessageRequest(BaseModel):
    """Consultation message request."""
    consultation_id: str
    message: str
    stream: bool = False


class OpponentAnalysisRequest(BaseModel):
    """Opponent analysis request."""
    consultation_id: str
    scenario: Dict[str, Any]


# Health and Status Endpoints
@router.get("/health")
async def mcp_health():
    """Check MCP services health."""
    try:
        initializer = get_mcp_initializer()
        health_status = await initializer.health_check()
        
        # Determine overall health
        is_healthy = (
            health_status.get("initialized", False) and
            not health_status.get("error")
        )
        
        return JSONResponse(
            status_code=200 if is_healthy else 503,
            content={
                "status": "healthy" if is_healthy else "unhealthy",
                "details": health_status
            }
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "error": str(e)}
        )


@router.get("/status")
async def mcp_status():
    """Get detailed MCP system status."""
    try:
        bridge = get_mcp_bridge()
        session_manager = get_session_manager()
        
        return JSONResponse({
            "bridge": bridge.get_status(),
            "sessions": session_manager.get_status(),
            "servers": bridge.get_status().get("servers", {})
        })
        
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Case Extraction Endpoints
@router.post("/case-extraction/chat/start")
async def start_chat_extraction():
    """Start a new chat-based case extraction session."""
    try:
        session_manager = get_session_manager()
        
        # Create new session
        session = await session_manager.create_session(
            client_id="api_client",
            metadata={"type": "chat_extraction"}
        )
        
        return JSONResponse({
            "success": True,
            "data": {
                "session_id": session.session_id,
                "status": "ready",
                "message": "Chat extraction session started. Please describe your case."
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to start chat extraction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/case-extraction/chat/message")
async def send_chat_message(request: ExtractChatRequest):
    """Send message in chat extraction session."""
    try:
        bridge = get_mcp_bridge()
        session_manager = get_session_manager()
        
        # Get or create session
        if request.session_id:
            session = await session_manager.get_session(request.session_id)
            if not session:
                raise ValueError("Invalid session ID")
        else:
            session = await session_manager.create_session(
                client_id="api_client",
                metadata={"type": "chat_extraction"}
            )
            
        # Call MCP extraction
        result = await bridge.call_tool(
            "case_extractor",
            "chat_extract",
            {
                "input": request.user_input,
                "context": request.context or session.context
            }
        )
        
        # Update session context
        await session_manager.update_context(
            session.session_id,
            result.get("extracted_info", {})
        )
        
        # Add to history
        await session_manager.add_to_history(
            session.session_id,
            "chat_extraction",
            {
                "input": request.user_input,
                "result": result
            }
        )
        
        return JSONResponse({
            "success": True,
            "data": {
                "session_id": session.session_id,
                "response": result.get("response"),
                "extracted_info": result.get("extracted_info"),
                "complete": result.get("complete", False)
            }
        })
        
    except Exception as e:
        logger.error(f"Chat message failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/case-extraction/file")
async def extract_from_file(
    file: Optional[UploadFile] = File(None),
    request: Optional[ExtractFileRequest] = None
):
    """Extract case information from a file."""
    try:
        bridge = get_mcp_bridge()
        
        # Get file content
        file_content = None
        file_type = "auto"
        
        if file:
            file_content = await file.read()
            file_content = file_content.decode('utf-8')
            file_type = file.filename.split('.')[-1] if '.' in file.filename else "auto"
        elif request and request.file_content:
            file_content = request.file_content
            file_type = request.file_type
        else:
            raise ValueError("No file provided")
            
        # Call MCP extraction
        result = await bridge.call_tool(
            "case_extractor",
            "extract_from_file",
            {
                "file_content": file_content,
                "file_type": file_type
            }
        )
        
        return JSONResponse({
            "success": True,
            "data": {
                "extracted_info": result.get("extracted_info"),
                "validation": result.get("validation"),
                "confidence": result.get("confidence", 0.0)
            }
        })
        
    except Exception as e:
        logger.error(f"File extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/case-extraction/validate")
async def validate_extraction(data: Dict[str, Any]):
    """Validate extracted case information."""
    try:
        bridge = get_mcp_bridge()
        
        result = await bridge.call_tool(
            "case_extractor",
            "validate_extraction",
            {"data": data}
        )
        
        return JSONResponse({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Legal Consultation Endpoints
@router.post("/consultation/init")
async def init_consultation(request: ConsultationInitRequest):
    """Initialize a legal consultation session."""
    try:
        bridge = get_mcp_bridge()
        session_manager = get_session_manager()
        
        # Create or get session
        if request.session_id:
            session = await session_manager.get_session(request.session_id)
        else:
            session = await session_manager.create_session(
                client_id="api_client",
                metadata={"type": "consultation"}
            )
            
        # Initialize consultation
        result = await bridge.call_tool(
            "lawyer_server",
            "init_consultation",
            {"case_data": request.case_data}
        )
        
        # Store consultation ID in session
        await session_manager.update_context(
            session.session_id,
            {"consultation_id": result.get("consultation_id")}
        )
        
        return JSONResponse({
            "success": True,
            "data": {
                "session_id": session.session_id,
                "consultation_id": result.get("consultation_id"),
                "status": "initialized",
                "initial_analysis": result.get("initial_analysis")
            }
        })
        
    except Exception as e:
        logger.error(f"Consultation init failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/consultation/message")
async def send_consultation_message(request: ConsultationMessageRequest):
    """Send a message in the consultation."""
    try:
        bridge = get_mcp_bridge()
        
        # Send message
        result = await bridge.call_tool(
            "lawyer_server",
            "send_message",
            {
                "consultation_id": request.consultation_id,
                "message": request.message
            }
        )
        
        return JSONResponse({
            "success": True,
            "data": {
                "consultation_id": request.consultation_id,
                "response": result.get("response"),
                "suggestions": result.get("suggestions", []),
                "references": result.get("references", [])
            }
        })
        
    except Exception as e:
        logger.error(f"Consultation message failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/consultation/message/stream")
async def stream_consultation_message(request: ConsultationMessageRequest):
    """Stream consultation response."""
    try:
        bridge = get_mcp_bridge()
        
        async def generate():
            """Generate streaming response."""
            # Call with streaming
            async for chunk in bridge.call_tool_stream(
                "lawyer_server",
                "send_message",
                {
                    "consultation_id": request.consultation_id,
                    "message": request.message,
                    "stream": True
                }
            ):
                yield f"data: {json.dumps(chunk)}\n\n"
                
        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )
        
    except Exception as e:
        logger.error(f"Streaming failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/consultation/opponent-analysis")
async def analyze_opponent(request: OpponentAnalysisRequest):
    """Perform opponent strategy analysis."""
    try:
        bridge = get_mcp_bridge()
        
        result = await bridge.call_tool(
            "lawyer_server",
            "simulate_opponent",
            {
                "consultation_id": request.consultation_id,
                "scenario": request.scenario
            }
        )
        
        return JSONResponse({
            "success": True,
            "data": {
                "consultation_id": request.consultation_id,
                "strategies": result.get("strategies", []),
                "counters": result.get("counters", []),
                "probabilities": result.get("probabilities", {}),
                "recommendations": result.get("recommendations", [])
            }
        })
        
    except Exception as e:
        logger.error(f"Opponent analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Tool Management Endpoints
@router.get("/tools/{server_name}")
async def list_server_tools(server_name: str):
    """List available tools for a specific server."""
    try:
        bridge = get_mcp_bridge()
        tools = await bridge.list_tools(server_name)
        
        return JSONResponse({
            "success": True,
            "data": {
                "server": server_name,
                "tools": tools
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/{server_name}/{tool_name}/call")
async def call_tool(
    server_name: str,
    tool_name: str,
    arguments: Dict[str, Any]
):
    """Call a specific tool on a server."""
    try:
        bridge = get_mcp_bridge()
        result = await bridge.call_tool(server_name, tool_name, arguments)
        
        return JSONResponse({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"Tool call failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Session Management Endpoints
@router.get("/sessions")
async def list_sessions():
    """List all active sessions."""
    try:
        session_manager = get_session_manager()
        # This would need implementation in session manager
        
        return JSONResponse({
            "success": True,
            "data": {
                "sessions": [],
                "count": 0
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details."""
    try:
        session_manager = get_session_manager()
        session = await session_manager.get_session(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        return JSONResponse({
            "success": True,
            "data": session.to_dict()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    try:
        session_manager = get_session_manager()
        await session_manager.destroy_session(session_id)
        
        return JSONResponse({
            "success": True,
            "message": "Session deleted"
        })
        
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Configuration Management
@router.post("/config/reload")
async def reload_configuration():
    """Reload MCP configuration."""
    try:
        initializer = get_mcp_initializer()
        await initializer.reload_config()
        
        return JSONResponse({
            "success": True,
            "message": "Configuration reloaded"
        })
        
    except Exception as e:
        logger.error(f"Failed to reload config: {e}")
        raise HTTPException(status_code=500, detail=str(e))