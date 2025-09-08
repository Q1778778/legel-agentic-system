"""API endpoints for OpenAI Agents SDK integration."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from typing import Dict, Any, Optional
import uuid
import structlog

from ..agents import (
    DebateOrchestrator,
    WorkflowEngine,
    ws_manager
)
from ..agents.orchestrator import DebateMode
from ..models.schemas import ArgumentBundle
from ..core.config import settings

logger = structlog.get_logger()

router = APIRouter()

# Store active orchestrators
active_debates: Dict[str, DebateOrchestrator] = {}
workflow_engine = WorkflowEngine()


# Initialize workflow definitions
def init_workflows():
    """Initialize standard workflows."""
    try:
        # Register debate workflow
        debate_workflow = workflow_engine.create_debate_workflow(
            max_turns=3,
            enable_feedback=True
        )
        workflow_engine.register_workflow(debate_workflow)
        
        # Register single analysis workflow
        single_workflow = workflow_engine.create_debate_workflow(
            max_turns=1,
            enable_feedback=True
        )
        single_workflow.id = "single_analysis_workflow"
        single_workflow.name = "Single Lawyer Analysis Workflow"
        workflow_engine.register_workflow(single_workflow)
        
        logger.info("Initialized workflow definitions")
    except Exception as e:
        logger.error(f"Failed to initialize workflows: {e}")


# Initialize on startup
init_workflows()


@router.post("/debate/start")
async def start_debate(
    case_id: str,
    issue_text: str,
    mode: str = "debate",
    lawyer_id: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    max_turns: int = 3,
    enable_feedback: bool = True,
    background_tasks: BackgroundTasks = BackgroundTasks()
) -> Dict[str, Any]:
    """Start a new legal debate session.
    
    Args:
        case_id: Case identifier
        issue_text: Legal issue to debate
        mode: Debate mode (single, debate, feedback)
        lawyer_id: Optional lawyer ID for retrieval
        jurisdiction: Optional jurisdiction filter
        max_turns: Maximum debate turns
        enable_feedback: Whether to include feedback agent
        background_tasks: FastAPI background tasks
        
    Returns:
        Session information
    """
    try:
        # Create session ID
        session_id = str(uuid.uuid4())
        
        # Create WebSocket session
        ws_manager.create_session(session_id)
        
        # Create orchestrator
        debate_mode = DebateMode(mode)
        orchestrator = DebateOrchestrator(
            mode=debate_mode,
            max_turns=max_turns,
            enable_feedback=enable_feedback,
            api_key=settings.openai_api_key
        )
        
        # Store orchestrator
        active_debates[session_id] = orchestrator
        
        # Start debate
        context = await orchestrator.start_debate(
            case_id=case_id,
            issue_text=issue_text,
            lawyer_id=lawyer_id,
            jurisdiction=jurisdiction
        )
        
        # Broadcast debate start
        await ws_manager.broadcast_debate_start(
            session_id=session_id,
            case_id=case_id,
            issue_text=issue_text,
            mode=mode
        )
        
        # Start background execution if auto-run is enabled
        if mode == "debate":
            background_tasks.add_task(
                run_debate_background,
                session_id,
                orchestrator
            )
        
        return {
            "session_id": session_id,
            "status": "started",
            "case_id": case_id,
            "issue": issue_text,
            "mode": mode,
            "max_turns": max_turns,
            "bundles_retrieved": len(context.bundles),
            "websocket_url": f"/api/v1/agents/ws/{session_id}"
        }
        
    except Exception as e:
        logger.error(f"Failed to start debate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debate/{session_id}/turn")
async def execute_turn(session_id: str) -> Dict[str, Any]:
    """Execute the next turn in a debate.
    
    Args:
        session_id: Session identifier
        
    Returns:
        Turn results
    """
    if session_id not in active_debates:
        raise HTTPException(status_code=404, detail="Session not found")
    
    orchestrator = active_debates[session_id]
    
    try:
        # Execute turn
        messages = await orchestrator.execute_turn()
        
        # Broadcast messages
        for message in messages:
            await ws_manager.broadcast_agent_message(session_id, message)
        
        # Broadcast turn complete
        await ws_manager.broadcast_turn_complete(
            session_id,
            orchestrator.context.current_turn,
            messages
        )
        
        # Check if debate is complete
        if orchestrator.state == "completed":
            summary = orchestrator.get_debate_summary()
            await ws_manager.broadcast_debate_end(session_id, summary)
        
        return {
            "session_id": session_id,
            "turn": orchestrator.context.current_turn,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content[:500] + "..." if len(msg.content) > 500 else msg.content,
                    "confidence": msg.confidence,
                    "citations": msg.citations
                }
                for msg in messages
            ],
            "state": orchestrator.state
        }
        
    except Exception as e:
        logger.error(f"Failed to execute turn: {e}")
        await ws_manager.broadcast_error(session_id, str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debate/{session_id}/status")
async def get_debate_status(session_id: str) -> Dict[str, Any]:
    """Get the current status of a debate.
    
    Args:
        session_id: Session identifier
        
    Returns:
        Debate status
    """
    if session_id not in active_debates:
        raise HTTPException(status_code=404, detail="Session not found")
    
    orchestrator = active_debates[session_id]
    summary = orchestrator.get_debate_summary()
    
    return summary


@router.post("/debate/{session_id}/stop")
async def stop_debate(session_id: str) -> Dict[str, Any]:
    """Stop an active debate.
    
    Args:
        session_id: Session identifier
        
    Returns:
        Final debate summary
    """
    if session_id not in active_debates:
        raise HTTPException(status_code=404, detail="Session not found")
    
    orchestrator = active_debates[session_id]
    summary = orchestrator.get_debate_summary()
    
    # Broadcast debate end
    await ws_manager.broadcast_debate_end(session_id, summary)
    
    # Clean up
    del active_debates[session_id]
    
    return summary


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time debate updates.
    
    Args:
        websocket: WebSocket connection
        session_id: Session to connect to
    """
    manager = await ws_manager.connect_to_session(websocket, session_id)
    
    try:
        while True:
            # Keep connection alive and handle client messages
            data = await websocket.receive_text()
            
            # Handle client commands
            if data == "ping":
                await ws_manager.send_heartbeat(session_id)
            elif data == "status":
                if session_id in active_debates:
                    orchestrator = active_debates[session_id]
                    summary = orchestrator.get_debate_summary()
                    await websocket.send_json(summary)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"WebSocket disconnected from session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@router.post("/workflow/execute")
async def execute_workflow(
    workflow_id: str,
    case_id: str,
    issue_text: str,
    lawyer_id: Optional[str] = None
) -> Dict[str, Any]:
    """Execute a predefined workflow.
    
    Args:
        workflow_id: Workflow to execute
        case_id: Case identifier
        issue_text: Legal issue
        lawyer_id: Optional lawyer ID
        
    Returns:
        Execution results
    """
    try:
        context = {
            "case_id": case_id,
            "issue_text": issue_text,
            "lawyer_id": lawyer_id
        }
        
        result = await workflow_engine.execute_workflow(workflow_id, context)
        
        return {
            "execution_id": result["id"],
            "workflow_id": workflow_id,
            "status": result["status"],
            "started_at": result["started_at"],
            "completed_at": result["completed_at"],
            "steps": result["steps"]
        }
        
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflow/{execution_id}/status")
async def get_workflow_status(execution_id: str) -> Dict[str, Any]:
    """Get workflow execution status.
    
    Args:
        execution_id: Execution identifier
        
    Returns:
        Execution status
    """
    try:
        status = await workflow_engine.get_execution_status(execution_id)
        return status
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get workflow status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Background task for auto-running debates
async def run_debate_background(session_id: str, orchestrator: DebateOrchestrator):
    """Run a complete debate in the background.
    
    Args:
        session_id: Session identifier
        orchestrator: Debate orchestrator
    """
    try:
        async for message in orchestrator.stream_debate():
            await ws_manager.broadcast_agent_message(session_id, message)
            
            # Broadcast turn complete after each pair of messages
            if orchestrator.context.current_turn > 0:
                await ws_manager.broadcast_turn_complete(
                    session_id,
                    orchestrator.context.current_turn,
                    [message]
                )
        
        # Broadcast debate end
        summary = orchestrator.get_debate_summary()
        await ws_manager.broadcast_debate_end(session_id, summary)
        
    except Exception as e:
        logger.error(f"Background debate execution failed: {e}")
        await ws_manager.broadcast_error(session_id, str(e))