"""
API endpoints for workflow management
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field
import logging

from ..services.workflow_engine import WorkflowEngine, WorkflowStatus

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/workflows", tags=["workflows"])

# Global workflow engine instance
workflow_engine = WorkflowEngine()


class WorkflowCreateRequest(BaseModel):
    """Request model for creating a workflow"""
    mode: str = Field(..., description="Workflow mode: 'single' or 'debate'")
    case_id: str = Field(..., description="Case identifier")
    issue_text: str = Field(..., description="Legal issue description")
    lawyer_id: Optional[str] = Field(None, description="Optional lawyer ID")
    jurisdiction: Optional[str] = Field(None, description="Optional jurisdiction")
    max_turns: int = Field(default=3, description="Maximum debate turns")
    model: str = Field(default="gpt-4o-mini", description="OpenAI model to use")


class WorkflowResponse(BaseModel):
    """Response model for workflow operations"""
    workflow_id: str
    status: str
    mode: str
    created_at: str
    metadata: Dict[str, Any]


class WorkflowExecuteRequest(BaseModel):
    """Request model for executing a workflow"""
    async_execution: bool = Field(default=True, description="Execute asynchronously")


@router.post("/", response_model=WorkflowResponse)
async def create_workflow(request: WorkflowCreateRequest) -> WorkflowResponse:
    """
    Create a new workflow
    
    Args:
        request: Workflow creation request
        
    Returns:
        Created workflow details
    """
    try:
        # Prepare input data
        input_data = {
            "case_id": request.case_id,
            "issue_text": request.issue_text,
            "lawyer_id": request.lawyer_id,
            "jurisdiction": request.jurisdiction,
            "max_turns": request.max_turns,
            "model": request.model
        }
        
        # Create workflow
        workflow = workflow_engine.create_workflow(
            mode=request.mode,
            input_data=input_data
        )
        
        return WorkflowResponse(
            workflow_id=workflow.workflow_id,
            status=workflow.status.value,
            mode=workflow.mode,
            created_at=workflow.created_at.isoformat(),
            metadata=workflow.metadata
        )
        
    except Exception as e:
        logger.error(f"Error creating workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}", response_model=Dict[str, Any])
async def get_workflow(workflow_id: str) -> Dict[str, Any]:
    """
    Get workflow details
    
    Args:
        workflow_id: Workflow ID
        
    Returns:
        Workflow details
    """
    workflow = workflow_engine.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return {
        "workflow_id": workflow.workflow_id,
        "status": workflow.status.value,
        "mode": workflow.mode,
        "current_step": workflow.current_step.value if workflow.current_step else None,
        "steps_completed": [step.value for step in workflow.steps_completed],
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
        "input_data": workflow.input_data,
        "output_data": workflow.output_data,
        "error": workflow.error,
        "metadata": workflow.metadata
    }


@router.post("/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    request: WorkflowExecuteRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Execute a workflow
    
    Args:
        workflow_id: Workflow ID
        request: Execution request
        background_tasks: FastAPI background tasks
        
    Returns:
        Execution status
    """
    workflow = workflow_engine.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if workflow.status != WorkflowStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Workflow is in {workflow.status.value} state, cannot execute"
        )
    
    if request.async_execution:
        # Execute in background
        # Use the internal method that doesn't require context
        background_tasks.add_task(workflow_engine._execute_workflow_internal, workflow_id)
        return {
            "message": "Workflow execution started",
            "workflow_id": workflow_id,
            "async": True
        }
    else:
        # Execute synchronously
        try:
            await workflow_engine._execute_workflow_internal(workflow_id)
            return {
                "message": "Workflow execution completed",
                "workflow_id": workflow_id,
                "async": False
            }
        except Exception as e:
            logger.error(f"Error executing workflow: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workflow_id}")
async def cancel_workflow(workflow_id: str) -> Dict[str, Any]:
    """
    Cancel a running workflow
    
    Args:
        workflow_id: Workflow ID
        
    Returns:
        Cancellation status
    """
    success = await workflow_engine.cancel_workflow(workflow_id)
    
    if not success:
        workflow = workflow_engine.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        else:
            return {
                "message": f"Workflow is in {workflow.status.value} state, cannot cancel",
                "workflow_id": workflow_id,
                "cancelled": False
            }
    
    return {
        "message": "Workflow cancelled successfully",
        "workflow_id": workflow_id,
        "cancelled": True
    }


@router.post("/{workflow_id}/cleanup")
async def cleanup_workflow(workflow_id: str) -> Dict[str, Any]:
    """
    Clean up workflow resources
    
    Args:
        workflow_id: Workflow ID
        
    Returns:
        Cleanup status
    """
    workflow = workflow_engine.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if workflow.status == WorkflowStatus.RUNNING:
        raise HTTPException(
            status_code=400,
            detail="Cannot cleanup running workflow"
        )
    
    workflow_engine.cleanup_workflow(workflow_id)
    
    return {
        "message": "Workflow cleaned up successfully",
        "workflow_id": workflow_id
    }


# Argumentation endpoints (simplified interface)

class ArgumentAnalysisRequest(BaseModel):
    """Request model for argument analysis"""
    argument: str = Field(..., description="Legal argument to analyze")
    role: str = Field(default="prosecutor", description="Role: prosecutor or defender")
    context: Optional[str] = Field(None, description="Additional context")


@router.post("/arguments/analyze")
async def analyze_argument(
    request: ArgumentAnalysisRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Analyze a single legal argument (simplified interface)
    
    Args:
        request: Argument analysis request
        background_tasks: FastAPI background tasks
        
    Returns:
        Analysis workflow details
    """
    # Create a single-mode workflow
    input_data = {
        "case_id": "analysis-" + str(hash(request.argument))[:8],
        "issue_text": request.argument,
        "lawyer_id": None,
        "jurisdiction": None,
        "max_turns": 1,
        "model": "gpt-4o-mini"
    }
    
    workflow = workflow_engine.create_workflow(
        mode="single",
        input_data=input_data
    )
    
    # Execute in background
    background_tasks.add_task(workflow_engine.execute_workflow, workflow.workflow_id)
    
    return {
        "workflow_id": workflow.workflow_id,
        "status": "started",
        "message": "Analysis started. Use workflow ID to check status."
    }


class DebateCreateRequest(BaseModel):
    """Request model for creating a debate"""
    case_id: str = Field(..., description="Case identifier")
    prosecution_strategy: str = Field(..., description="Prosecution strategy")
    case_facts: str = Field(..., description="Case facts and context")
    max_turns: int = Field(default=3, description="Maximum debate turns")


@router.post("/debates/create")
async def create_debate(
    request: DebateCreateRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Create a debate session (simplified interface)
    
    Args:
        request: Debate creation request
        background_tasks: FastAPI background tasks
        
    Returns:
        Debate workflow details
    """
    # Create a debate-mode workflow
    issue_text = f"Case Facts: {request.case_facts}\n\nProsecution Strategy: {request.prosecution_strategy}"
    
    input_data = {
        "case_id": request.case_id,
        "issue_text": issue_text,
        "lawyer_id": None,
        "jurisdiction": None,
        "max_turns": request.max_turns,
        "model": "gpt-4o-mini"
    }
    
    workflow = workflow_engine.create_workflow(
        mode="debate",
        input_data=input_data
    )
    
    # Execute in background
    background_tasks.add_task(workflow_engine.execute_workflow, workflow.workflow_id)
    
    return {
        "workflow_id": workflow.workflow_id,
        "debate_id": workflow.workflow_id,  # Same as workflow ID
        "status": "started",
        "message": "Debate started. Use workflow ID to check status."
    }


@router.get("/debates/{debate_id}/history")
async def get_debate_history(debate_id: str) -> Dict[str, Any]:
    """
    Get debate transcript
    
    Args:
        debate_id: Debate ID (same as workflow ID)
        
    Returns:
        Debate transcript
    """
    workflow = workflow_engine.get_workflow(debate_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Debate not found")
    
    # Extract messages from output data
    messages = workflow.output_data.get("debate_messages", [])
    
    return {
        "debate_id": debate_id,
        "status": workflow.status.value,
        "turns": workflow.output_data.get("summary", {}).get("total_turns", 0),
        "messages": messages,
        "summary": workflow.output_data.get("summary", {}),
        "feedback": workflow.output_data.get("feedback", {})
    }