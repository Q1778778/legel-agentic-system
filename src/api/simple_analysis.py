"""
Simple Analysis API - Direct GPT-based generation without databases
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
import structlog
from pydantic import BaseModel
import time

from ..services.bundle_generator import BundleGenerator
from ..services.legal_analysis_service import LegalAnalysisService
from ..models.schemas import AnalysisRequest

logger = structlog.get_logger()
router = APIRouter()

# Initialize services
bundle_generator = BundleGenerator()
analysis_service = LegalAnalysisService()


class SimpleAnalysisRequest(BaseModel):
    """Simple request with just context"""
    context: str
    num_precedents: int = 3
    include_prosecution: bool = True
    include_judge: bool = True
    max_length: int = 1000


@router.post(
    "/generate",
    summary="Simple argument generation",
    description="Generate arguments with GPT-created precedents (no database needed)"
)
async def simple_generate(request: SimpleAnalysisRequest):
    """Simple generation using GPT for everything
    
    This endpoint:
    1. Uses GPT to generate relevant precedent cases based on context
    2. Uses those precedents to generate multi-agent arguments
    3. No database access needed!
    
    Args:
        request: Simple analysis request with just context
        
    Returns:
        Generated arguments with GPT-created precedents
    """
    
    start_time = time.time()
    
    try:
        logger.info("Starting simple analysis")
        
        # Step 1: Generate relevant bundles using GPT
        logger.info(f"Generating {request.num_precedents} precedents with GPT")
        bundles = await bundle_generator.generate_bundles_from_context(
            context=request.context,
            num_bundles=request.num_precedents
        )
        
        logger.info(f"Generated {len(bundles)} bundles")
        
        # Step 2: Generate arguments using analysis
        analysis_request = AnalysisRequest(
            bundles=bundles,
            context=request.context,
            include_prosecution=request.include_prosecution,
            include_judge=request.include_judge,
            max_length=request.max_length
        )
        
        analysis_response = await analysis_service.analyze(analysis_request)
        
        # Calculate total time
        generation_time_ms = int((time.time() - start_time) * 1000)
        
        # Build response
        response = {
            "status": "success",
            "precedents_used": [
                {
                    "case": bundle.case.caption,
                    "issue": bundle.issue.title,
                    "relevance": bundle.confidence.get("value", 0)
                }
                for bundle in bundles
            ],
            "defense": analysis_response.defense.dict() if analysis_response.defense else None,
            "prosecution": analysis_response.prosecution.dict() if analysis_response.prosecution else None,
            "judge": analysis_response.judge.dict() if analysis_response.judge else None,
            "overall_confidence": analysis_response.overall_confidence,
            "generation_time_ms": generation_time_ms,
            "method": "GPT-generated precedents (no database)"
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Simple analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))