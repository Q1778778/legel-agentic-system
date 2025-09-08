"""
Smart Analysis API - Automatically parses context and retrieves relevant cases
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
import structlog
from pydantic import BaseModel

from ..services.context_parser import ContextParser
from ..services.graphrag_retrieval import GraphRAGRetrieval
from ..services.legal_analysis_service import LegalAnalysisService
from ..models.schemas import RetrievalRequest, AnalysisRequest

logger = structlog.get_logger()
router = APIRouter()

# Initialize services
context_parser = ContextParser()
retrieval_service = GraphRAGRetrieval()
analysis_service = LegalAnalysisService()


class SmartAnalysisRequest(BaseModel):
    """Request for smart analysis with auto-parsing"""
    context: str
    auto_retrieve: bool = True
    include_prosecution: bool = True
    include_judge: bool = True
    max_length: int = 1000
    retrieval_limit: int = 5
    lawyer_id: Optional[str] = None


class SmartAnalysisResponse(BaseModel):
    """Response with parsed context, retrieved cases, and generated arguments"""
    parsed_context: dict
    retrieved_cases: Optional[dict] = None
    defense: Optional[dict] = None
    prosecution: Optional[dict] = None
    judge: Optional[dict] = None
    overall_confidence: float
    generation_time_ms: int


@router.post(
    "/smart-analyze",
    response_model=SmartAnalysisResponse,
    summary="Smart legal argument analysis",
    description="Automatically parse context, retrieve cases, and generate arguments"
)
async def smart_analyze(request: SmartAnalysisRequest) -> SmartAnalysisResponse:
    """Smart analysis with automatic context parsing and case retrieval
    
    This endpoint:
    1. Parses the context using GPT to extract key information
    2. Automatically retrieves relevant cases using GraphRAG
    3. Generates multi-agent arguments based on the cases
    
    Args:
        request: Smart analysis request
        
    Returns:
        Complete response with all steps
    """
    
    import time
    start_time = time.time()
    
    try:
        # Step 1: Parse context using GPT
        logger.info("Parsing context with GPT")
        parsed = await context_parser.parse_context(request.context)
        
        # Step 2: Retrieve relevant cases if auto_retrieve is enabled
        bundles = []
        retrieval_result = None
        
        if request.auto_retrieve:
            logger.info(f"Auto-retrieving cases for: {parsed['search_query']}")
            
            # Ensure issue_text is provided for retrieval
            search_query = parsed.get("search_query") or parsed.get("issue_type") or context[:100]
            
            retrieval_request = RetrievalRequest(
                issue_text=search_query,
                tenant="default",
                limit=request.retrieval_limit,
                lawyer_id=request.lawyer_id if request.lawyer_id else None,
                jurisdiction=parsed.get("jurisdiction") if parsed.get("jurisdiction") else None
            )
            
            retrieval_response = await retrieval_service.retrieve_past_defenses(retrieval_request)
            bundles = retrieval_response.bundles
            
            retrieval_result = {
                "total_count": retrieval_response.total_count,
                "query_time_ms": retrieval_response.query_time_ms,
                "query_used": parsed["search_query"]
            }
            
            logger.info(f"Retrieved {len(bundles)} relevant cases")
        
        # Step 3: Generate arguments using analysis
        analysis_request = AnalysisRequest(
            bundles=bundles if bundles else [],  # Can work without bundles
            context=request.context,
            include_prosecution=request.include_prosecution,
            include_judge=request.include_judge,
            max_length=request.max_length
        )
        
        analysis_response = await analysis_service.analyze(analysis_request)
        
        # Calculate total time
        generation_time_ms = int((time.time() - start_time) * 1000)
        
        # Build response
        return SmartAnalysisResponse(
            parsed_context=parsed,
            retrieved_cases=retrieval_result,
            defense=analysis_response.defense.dict() if analysis_response.defense else None,
            prosecution=analysis_response.prosecution.dict() if analysis_response.prosecution else None,
            judge=analysis_response.judge.dict() if analysis_response.judge else None,
            overall_confidence=analysis_response.overall_confidence,
            generation_time_ms=generation_time_ms
        )
        
    except Exception as e:
        logger.error(f"Smart analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))