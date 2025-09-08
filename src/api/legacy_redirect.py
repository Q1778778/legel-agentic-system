"""
Legacy Redirect API - Maintains backward compatibility
Redirects old simulation endpoints to new legal workflow system
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
from typing import Optional, Dict, Any
import structlog
from pydantic import BaseModel

from .legal_analysis import (
    LegalCaseRequest,
    ExpectedArgumentRequest,
    analyze_legal_case,
    generate_legal_arguments,
    generate_expected_argument
)
from ..models.schemas import SimulationRequest, SimulationResponse, SimulationArtifact

logger = structlog.get_logger()
router = APIRouter()


@router.post(
    "/simulate",
    summary="[DEPRECATED] Use /api/v1/analysis/analyze-case instead",
    description="Legacy endpoint - redirects to new legal analysis system",
    deprecated=True
)
async def simulate_arguments_legacy(request: SimulationRequest):
    """
    Legacy simulation endpoint - redirects to new legal analysis
    
    This endpoint is maintained for backward compatibility.
    Please use /api/v1/analysis/analyze-case for new implementations.
    """
    logger.warning("Legacy /simulate endpoint called - redirecting to new system")
    
    # Convert legacy request to new format
    context = request.context or "Legal case analysis"
    if request.bundles:
        # Extract context from bundles if available
        first_bundle = request.bundles[0]
        context = f"{first_bundle.issue.title}. Case: {first_bundle.case.caption}"
    
    new_request = LegalCaseRequest(
        context=context,
        case_id=f"legacy_{request.bundles[0].case.id if request.bundles else 'unknown'}",
        auto_retrieve=False,  # Don't retrieve again if bundles provided
        include_prosecution=request.include_prosecution,
        include_judge=request.include_judge,
        max_length=request.max_length
    )
    
    # Call new endpoint
    response = await analyze_legal_case(new_request)
    
    # Convert response to legacy format
    defense_artifact = None
    if response.defense_argument:
        defense_artifact = SimulationArtifact(
            text=response.defense_argument["content"],
            confidence=response.defense_argument.get("confidence", 0.8),
            role="defense",
            citations_used=[]
        )
    
    prosecution_artifact = None
    if response.prosecution_argument:
        prosecution_artifact = SimulationArtifact(
            text=response.prosecution_argument["content"],
            confidence=response.prosecution_argument.get("confidence", 0.8),
            role="prosecution",
            citations_used=[]
        )
    
    judge_artifact = None
    if response.judicial_analysis:
        judge_artifact = SimulationArtifact(
            text=response.judicial_analysis["content"],
            confidence=0.85,
            role="judge",
            citations_used=[]
        )
    
    return SimulationResponse(
        defense=defense_artifact,
        prosecution=prosecution_artifact,
        judge=judge_artifact,
        script=None,
        overall_confidence=response.confidence_score,
        generation_time_ms=response.execution_time_ms
    )


@router.post(
    "/expected-argument",
    summary="[DEPRECATED] Use /api/v1/analysis/expected-argument instead",
    description="Legacy endpoint - redirects to new expected argument system",
    deprecated=True
)
async def generate_expected_argument_legacy(request: SimulationRequest):
    """
    Legacy expected argument endpoint - redirects to new system
    
    This endpoint is maintained for backward compatibility.
    Please use /api/v1/analysis/expected-argument for new implementations.
    """
    logger.warning("Legacy /expected-argument endpoint called - redirecting to new system")
    
    # Convert to new format
    new_request = ExpectedArgumentRequest(
        context=request.context or "Legal case",
        retrieve_precedents=len(request.bundles) == 0 if request.bundles is not None else True,
        precedent_limit=5
    )
    
    # Call new endpoint
    response = await generate_expected_argument(new_request)
    
    # Convert to legacy format
    defense_text = ""
    prosecution_text = ""
    judge_text = ""
    
    if response["expected_arguments"]["defense"]:
        defense_text = response["expected_arguments"]["defense"][0]["argument"]
    
    if response["expected_arguments"]["prosecution"]:
        prosecution_text = response["expected_arguments"]["prosecution"][0]["argument"]
    
    if response["expected_arguments"]["judicial_concerns"]:
        judge_text = response["expected_arguments"]["judicial_concerns"][0]["concern"]
    
    return SimulationResponse(
        defense=SimulationArtifact(
            text=defense_text,
            confidence=0.85,
            role="defense",
            citations_used=[]
        ),
        prosecution=SimulationArtifact(
            text=prosecution_text,
            confidence=0.82,
            role="prosecution",
            citations_used=[]
        ),
        judge=SimulationArtifact(
            text=judge_text,
            confidence=0.85,
            role="judge",
            citations_used=[]
        ),
        script=None,
        overall_confidence=response["confidence_score"],
        generation_time_ms=response["execution_time_ms"]
    )


class SmartSimulationRequest(BaseModel):
    """Legacy smart simulation request"""
    context: str
    auto_retrieve: bool = True
    include_prosecution: bool = True
    include_judge: bool = True
    max_length: int = 1000
    retrieval_limit: int = 5
    lawyer_id: Optional[str] = None


@router.post(
    "/smart-simulate",
    summary="[DEPRECATED] Use /api/v1/analysis/analyze-case instead",
    description="Legacy smart simulation - redirects to new analysis system",
    deprecated=True
)
async def smart_simulate_legacy(request: SmartSimulationRequest):
    """
    Legacy smart simulation endpoint - redirects to new legal analysis
    
    This endpoint is maintained for backward compatibility.
    Please use /api/v1/analysis/analyze-case for new implementations.
    """
    logger.warning("Legacy /smart-simulate endpoint called - redirecting to new system")
    
    # Convert to new format
    new_request = LegalCaseRequest(
        context=request.context,
        lawyer_id=request.lawyer_id,
        auto_retrieve=request.auto_retrieve,
        retrieval_limit=request.retrieval_limit,
        include_prosecution=request.include_prosecution,
        include_judge=request.include_judge,
        max_length=request.max_length
    )
    
    # Call new endpoint
    response = await analyze_legal_case(new_request)
    
    # Convert to legacy format
    return {
        "parsed_context": response.parsed_context,
        "retrieved_cases": {
            "total_count": len(response.retrieved_precedents) if response.retrieved_precedents else 0,
            "query_time_ms": 100,
            "query_used": response.parsed_context.get("search_query", "")
        } if response.retrieved_precedents else None,
        "defense": response.defense_argument,
        "prosecution": response.prosecution_argument,
        "judge": response.judicial_analysis,
        "overall_confidence": response.confidence_score,
        "generation_time_ms": response.execution_time_ms
    }


class SimpleSimulationRequest(BaseModel):
    """Legacy simple simulation request"""
    context: str
    num_precedents: int = 3
    include_prosecution: bool = True
    include_judge: bool = True
    max_length: int = 1000


@router.post(
    "/generate",
    summary="[DEPRECATED] Use /api/v1/analysis/generate-arguments instead",
    description="Legacy simple generation - redirects to new argument generation",
    deprecated=True
)
async def simple_generate_legacy(request: SimpleSimulationRequest):
    """
    Legacy simple generation endpoint - redirects to new system
    
    This endpoint is maintained for backward compatibility.
    Please use /api/v1/analysis/generate-arguments for new implementations.
    """
    logger.warning("Legacy /generate endpoint called - redirecting to new system")
    
    # Convert to new format
    new_request = LegalCaseRequest(
        context=request.context,
        auto_retrieve=False,  # Simple mode doesn't use retrieval
        include_prosecution=request.include_prosecution,
        include_judge=request.include_judge,
        max_length=request.max_length
    )
    
    # Call new endpoint
    response = await generate_legal_arguments(new_request)
    
    # Convert to legacy format
    return {
        "status": response["status"],
        "precedents_used": [],  # No precedents in fast mode
        "defense": response["defense_argument"],
        "prosecution": response["prosecution_argument"],
        "judge": response["judicial_analysis"],
        "overall_confidence": response["confidence_score"],
        "generation_time_ms": response["execution_time_ms"],
        "method": response["method"]
    }