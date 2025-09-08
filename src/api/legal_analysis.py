"""Legal Analysis API endpoints."""

from fastapi import APIRouter, HTTPException, status
import structlog

from ..models.schemas import AnalysisRequest, AnalysisResponse
from ..services.legal_analysis_service import LegalAnalysisService

logger = structlog.get_logger()
router = APIRouter()

# Initialize legal analysis service
analysis_service = LegalAnalysisService()


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    summary="Analyze legal arguments",
    description="Generate defense, prosecution, and judge legal arguments",
)
async def analyze_arguments(request: AnalysisRequest) -> AnalysisResponse:
    """Analyze legal arguments based on retrieved bundles.
    
    Args:
        request: Analysis request with argument bundles
        
    Returns:
        Response with analyzed arguments
        
    Raises:
        HTTPException: If analysis fails
    """
    try:
        # Bundles are optional - can generate without historical cases
        bundle_count = len(request.bundles) if request.bundles else 0
        
        logger.info(
            "Analyzing arguments",
            bundle_count=bundle_count,
            include_prosecution=request.include_prosecution,
            include_judge=request.include_judge,
        )
        
        response = await analysis_service.analyze(request)
        
        return response
        
    except ValueError as e:
        logger.error(f"Invalid analysis request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error analyzing arguments: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analysis failed",
        )


@router.post(
    "/expected-argument",
    response_model=AnalysisResponse,
    summary="Generate expected argument",
    description="Generate expected argument for upcoming case",
)
async def generate_expected_argument(request: AnalysisRequest) -> AnalysisResponse:
    """Generate expected argument for upcoming case.
    
    Args:
        request: Analysis request with context
        
    Returns:
        Response with expected argument
        
    Raises:
        HTTPException: If generation fails
    """
    try:
        logger.info("Generating expected argument")
        
        # Force include all roles for expected argument
        request.include_prosecution = True
        request.include_judge = True
        
        response = await analysis_service.analyze(request)
        
        return response
        
    except Exception as e:
        logger.error(f"Error generating expected argument: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate expected argument",
        )