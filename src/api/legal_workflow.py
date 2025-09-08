"""
Legal Workflow API - Production-ready legal argument analysis system
"""

from fastapi import APIRouter, HTTPException, status
from typing import Optional, Dict, Any
import structlog
from pydantic import BaseModel

from ..services.debate_orchestrator import DebateOrchestrator, DebateMode
from ..services.workflow_engine import WorkflowEngine
from ..models.schemas import RetrievalRequest, ArgumentBundle

logger = structlog.get_logger()
router = APIRouter()

# Initialize workflow engine
workflow_engine = WorkflowEngine()


class LegalAnalysisRequest(BaseModel):
    """Request for legal analysis"""
    case_id: str
    issue_text: str
    lawyer_id: Optional[str] = None
    jurisdiction: Optional[str] = None
    max_turns: int = 3
    model: str = "gpt-4o-mini"
    include_prosecution: bool = True
    include_feedback: bool = True


class LegalDebateRequest(BaseModel):
    """Request for legal debate workflow"""
    case_id: str
    issue_text: str
    lawyer_id: Optional[str] = None
    jurisdiction: Optional[str] = None
    max_debate_rounds: int = 3
    model: str = "gpt-4o-mini"


class WorkflowResponse(BaseModel):
    """Response from workflow execution"""
    workflow_id: str
    status: str
    case_id: str
    issue_text: str
    arguments: Dict[str, Any]
    feedback: Optional[Dict[str, Any]] = None
    precedents_used: int
    confidence_score: float
    execution_time_ms: int


@router.post(
    "/analyze",
    response_model=WorkflowResponse,
    summary="Analyze legal arguments",
    description="Perform comprehensive legal analysis with AI agents"
)
async def analyze_legal_case(request: LegalAnalysisRequest) -> WorkflowResponse:
    """
    Analyze a legal case using AI-powered workflow
    
    This endpoint:
    1. Retrieves relevant precedents from GraphRAG
    2. Generates prosecution and defense arguments
    3. Provides judicial feedback and analysis
    
    Args:
        request: Legal analysis request
        
    Returns:
        Comprehensive legal analysis
    """
    import time
    start_time = time.time()
    
    try:
        logger.info(f"Starting legal analysis for case {request.case_id}")
        
        # Create workflow
        workflow = workflow_engine.create_workflow(
            mode="debate" if request.include_prosecution else "single",
            input_data={
                "case_id": request.case_id,
                "issue_text": request.issue_text,
                "lawyer_id": request.lawyer_id,
                "jurisdiction": request.jurisdiction,
                "max_turns": request.max_turns,
                "model": request.model
            }
        )
        
        # Execute workflow
        completed_workflow = await workflow_engine.execute_workflow(workflow.workflow_id)
        
        # Extract results
        output_data = completed_workflow.output_data
        messages = output_data.get("debate_messages", [])
        
        # Organize arguments by role
        arguments = {
            "defense": None,
            "prosecution": None,
            "judicial_review": None
        }
        
        for msg in messages:
            role = msg.get("role")
            if role == "defender":
                arguments["defense"] = {
                    "content": msg.get("content"),
                    "confidence": 0.85,
                    "timestamp": msg.get("timestamp")
                }
            elif role == "prosecutor":
                arguments["prosecution"] = {
                    "content": msg.get("content"),
                    "confidence": 0.82,
                    "timestamp": msg.get("timestamp")
                }
            elif role == "feedback":
                arguments["judicial_review"] = {
                    "content": msg.get("content"),
                    "analysis": "comprehensive",
                    "timestamp": msg.get("timestamp")
                }
        
        # Calculate confidence score
        summary = output_data.get("summary", {})
        confidence_score = 0.8  # Base confidence
        if summary.get("bundles_used", 0) > 3:
            confidence_score = 0.9
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        response = WorkflowResponse(
            workflow_id=workflow.workflow_id,
            status="completed",
            case_id=request.case_id,
            issue_text=request.issue_text,
            arguments=arguments,
            feedback=output_data.get("feedback"),
            precedents_used=output_data.get("context", {}).get("bundles_retrieved", 0),
            confidence_score=confidence_score,
            execution_time_ms=execution_time_ms
        )
        
        # Clean up workflow
        workflow_engine.cleanup_workflow(workflow.workflow_id)
        
        return response
        
    except Exception as e:
        logger.error(f"Legal analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Legal analysis workflow failed"
        )


@router.post(
    "/debate",
    response_model=WorkflowResponse,
    summary="Conduct legal debate",
    description="Run a multi-agent legal debate with prosecution and defense"
)
async def conduct_legal_debate(request: LegalDebateRequest) -> WorkflowResponse:
    """
    Conduct a structured legal debate
    
    This endpoint orchestrates a full legal debate between:
    - Prosecution agent
    - Defense agent
    - Judicial feedback agent
    
    Args:
        request: Legal debate request
        
    Returns:
        Complete debate transcript and analysis
    """
    import time
    start_time = time.time()
    
    try:
        logger.info(f"Starting legal debate for case {request.case_id}")
        
        # Create debate orchestrator directly
        orchestrator = DebateOrchestrator(
            mode=DebateMode.DEBATE,
            max_turns=request.max_debate_rounds,
            model=request.model
        )
        
        # Start debate
        context = await orchestrator.start_debate(
            case_id=request.case_id,
            issue_text=request.issue_text,
            lawyer_id=request.lawyer_id,
            jurisdiction=request.jurisdiction
        )
        
        # Run complete debate
        await orchestrator.run_complete_debate()
        
        # Get results
        summary = orchestrator.get_debate_summary()
        messages = orchestrator.get_messages()
        
        # Organize debate results
        arguments = {
            "defense": [],
            "prosecution": [],
            "judicial_review": None
        }
        
        for msg in messages:
            role = msg.get("role")
            content = {
                "content": msg.get("content"),
                "timestamp": msg.get("timestamp")
            }
            
            if role == "defender":
                arguments["defense"].append(content)
            elif role == "prosecutor":
                arguments["prosecution"].append(content)
            elif role == "feedback":
                arguments["judicial_review"] = content
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        return WorkflowResponse(
            workflow_id=request.case_id,
            status="completed",
            case_id=request.case_id,
            issue_text=request.issue_text,
            arguments=arguments,
            feedback=arguments.get("judicial_review"),
            precedents_used=summary.get("bundles_used", 0),
            confidence_score=0.85,
            execution_time_ms=execution_time_ms
        )
        
    except Exception as e:
        logger.error(f"Legal debate failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Legal debate workflow failed"
        )


@router.post(
    "/quick-analysis",
    summary="Quick legal analysis",
    description="Fast legal analysis without database lookups"
)
async def quick_legal_analysis(request: LegalAnalysisRequest):
    """
    Quick legal analysis using AI without GraphRAG retrieval
    
    This is a streamlined version that:
    1. Uses AI to generate relevant precedents
    2. Produces legal arguments quickly
    3. Suitable for rapid prototyping or demos
    
    Args:
        request: Legal analysis request
        
    Returns:
        Quick legal analysis results
    """
    import time
    start_time = time.time()
    
    try:
        logger.info(f"Starting quick analysis for case {request.case_id}")
        
        # Create a simple orchestrator
        orchestrator = DebateOrchestrator(
            mode=DebateMode.SINGLE if not request.include_prosecution else DebateMode.DEBATE,
            max_turns=1,  # Quick analysis with single round
            model=request.model
        )
        
        # Create mock context without retrieval
        from ..services.legal_agents import LegalContext
        context = LegalContext(
            case_id=request.case_id,
            issue_text=request.issue_text,
            max_turns=1,
            bundles=[],  # No retrieval for quick analysis
            metadata={"mode": "quick", "model": request.model}
        )
        
        # Set context directly
        orchestrator.context = context
        orchestrator.state = orchestrator.state.__class__.DEBATING
        
        # Generate arguments
        defense_response = await orchestrator.agent_orchestrator.run_agent_turn("defender", context)
        
        arguments = {
            "defense": {
                "content": defense_response.get("content"),
                "confidence": 0.75,
                "timestamp": defense_response.get("timestamp")
            }
        }
        
        if request.include_prosecution:
            pros_response = await orchestrator.agent_orchestrator.run_agent_turn("prosecutor", context)
            arguments["prosecution"] = {
                "content": pros_response.get("content"),
                "confidence": 0.75,
                "timestamp": pros_response.get("timestamp")
            }
        
        if request.include_feedback:
            feedback_response = await orchestrator.agent_orchestrator.run_agent_turn("feedback", context)
            arguments["judicial_review"] = {
                "content": feedback_response.get("content"),
                "timestamp": feedback_response.get("timestamp")
            }
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        return {
            "status": "success",
            "case_id": request.case_id,
            "issue_text": request.issue_text,
            "arguments": arguments,
            "method": "AI-generated analysis (no database)",
            "confidence_score": 0.75,
            "execution_time_ms": execution_time_ms
        }
        
    except Exception as e:
        logger.error(f"Quick analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Quick analysis failed"
        )


@router.get(
    "/workflow/{workflow_id}",
    summary="Get workflow status",
    description="Get the status of a legal workflow"
)
async def get_workflow_status(workflow_id: str):
    """
    Get the status of a workflow
    
    Args:
        workflow_id: Workflow identifier
        
    Returns:
        Workflow status and results
    """
    workflow = workflow_engine.get_workflow(workflow_id)
    
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found"
        )
    
    return {
        "workflow_id": workflow.workflow_id,
        "status": workflow.status.value,
        "current_step": workflow.current_step.value if workflow.current_step else None,
        "steps_completed": [step.value for step in workflow.steps_completed],
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
        "error": workflow.error
    }