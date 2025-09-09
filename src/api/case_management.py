"""
Case Management API endpoints.

This module provides HTTP API endpoints for CRUD operations on legal cases,
integrating with MCP servers for case extraction and analysis.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
import uuid
import logging
from datetime import datetime

from ..models.schemas import CaseCreate, CaseUpdate, CaseResponse, CaseListResponse
from ..services.case_service import case_service
from ..services.mcp_bridge import mcp_bridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cases", tags=["Case Management"])


@router.post("/", response_model=CaseResponse)
async def create_case(case_data: CaseCreate):
    """Create a new legal case."""
    try:
        # Generate unique case ID
        case_id = str(uuid.uuid4())
        
        # Create case with service
        case = await case_service.create_case(case_id, case_data.dict())
        
        if not case:
            raise HTTPException(status_code=400, detail="Failed to create case")
        
        logger.info(f"Created new case: {case_id}")
        return case
        
    except Exception as e:
        logger.error(f"Error creating case: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=CaseListResponse)
async def list_cases(
    skip: int = 0, 
    limit: int = 20,
    status: Optional[str] = None,
    created_by: Optional[str] = None
):
    """List all legal cases with optional filtering."""
    try:
        cases = await case_service.list_cases(
            skip=skip,
            limit=limit,
            status=status,
            created_by=created_by
        )
        
        total_count = await case_service.count_cases(status=status, created_by=created_by)
        
        return CaseListResponse(
            cases=cases,
            total_count=total_count,
            skip=skip,
            limit=limit
        )
        
    except Exception as e:
        logger.error(f"Error listing cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(case_id: str):
    """Get a specific legal case by ID."""
    try:
        case = await case_service.get_case(case_id)
        
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        
        return case
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting case {case_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{case_id}", response_model=CaseResponse)
async def update_case(case_id: str, case_update: CaseUpdate):
    """Update a legal case."""
    try:
        case = await case_service.update_case(case_id, case_update.dict(exclude_unset=True))
        
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        
        logger.info(f"Updated case: {case_id}")
        return case
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating case {case_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{case_id}")
async def delete_case(case_id: str):
    """Delete a legal case."""
    try:
        success = await case_service.delete_case(case_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Case not found")
        
        logger.info(f"Deleted case: {case_id}")
        return {"message": "Case deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting case {case_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{case_id}/documents")
async def add_case_document(case_id: str, document_info: Dict[str, Any]):
    """Add a document to a case."""
    try:
        case = await case_service.get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        
        document = await case_service.add_document(case_id, document_info)
        
        logger.info(f"Added document to case {case_id}: {document.get('id')}")
        return {"message": "Document added successfully", "document": document}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding document to case {case_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{case_id}/documents")
async def get_case_documents(case_id: str):
    """Get all documents for a case."""
    try:
        case = await case_service.get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        
        documents = await case_service.get_documents(case_id)
        
        return {"documents": documents}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting documents for case {case_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{case_id}/analysis-sessions")
async def start_analysis_session(case_id: str, query: str):
    """Start a legal analysis session for a case."""
    try:
        case = await case_service.get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        
        # Create session
        session_id = str(uuid.uuid4())
        session_data = {
            "id": session_id,
            "case_id": case_id,
            "started_at": datetime.now().isoformat(),
            "status": "active",
            "initial_query": query
        }
        
        # Start consultation with lawyer server
        case_context = {
            "case_id": case_id,
            "title": case.get("title"),
            "description": case.get("description"),
            "parties": case.get("parties", []),
            "issues": case.get("issues", []),
            "documents": await case_service.get_documents(case_id)
        }
        
        result = await mcp_bridge.legal_consultation(case_context, query)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        # Save session
        session_data["chat_history"] = [
            {"role": "user", "content": query, "timestamp": datetime.now().isoformat()},
            {"role": "assistant", "content": result.get("response", ""), "timestamp": datetime.now().isoformat()}
        ]
        
        await case_service.save_analysis_session(session_id, session_data)
        
        logger.info(f"Started analysis session for case {case_id}: {session_id}")
        return {
            "session_id": session_id,
            "response": result.get("response", ""),
            "analysis": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting analysis session for case {case_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{case_id}/analysis-sessions/{session_id}/continue")
async def continue_analysis_session(case_id: str, session_id: str, query: str):
    """Continue an existing analysis session."""
    try:
        case = await case_service.get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        
        session = await case_service.get_analysis_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Analysis session not found")
        
        # Get case context
        case_context = {
            "case_id": case_id,
            "title": case.get("title"),
            "description": case.get("description"),
            "parties": case.get("parties", []),
            "issues": case.get("issues", []),
            "documents": await case_service.get_documents(case_id),
            "chat_history": session.get("chat_history", [])
        }
        
        result = await mcp_bridge.legal_consultation(case_context, query)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        # Update session with new interaction
        new_interaction = [
            {"role": "user", "content": query, "timestamp": datetime.now().isoformat()},
            {"role": "assistant", "content": result.get("response", ""), "timestamp": datetime.now().isoformat()}
        ]
        
        await case_service.update_analysis_session(session_id, {
            "chat_history": session.get("chat_history", []) + new_interaction,
            "last_updated": datetime.now().isoformat()
        })
        
        return {
            "response": result.get("response", ""),
            "analysis": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error continuing analysis session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{case_id}/analysis-sessions")
async def get_analysis_sessions(case_id: str):
    """Get all analysis sessions for a case."""
    try:
        case = await case_service.get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        
        sessions = await case_service.get_case_analysis_sessions(case_id)
        
        return {"sessions": sessions}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis sessions for case {case_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{case_id}/analysis-sessions/{session_id}")
async def get_analysis_session(case_id: str, session_id: str):
    """Get a specific analysis session."""
    try:
        case = await case_service.get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        
        session = await case_service.get_analysis_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Analysis session not found")
        
        return session
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))