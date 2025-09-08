"""Retrieval API endpoints."""

from fastapi import APIRouter, HTTPException, status
from typing import Optional
import structlog

from ..models.schemas import RetrievalRequest, RetrievalResponse
from ..services.graphrag_retrieval import GraphRAGRetrieval

logger = structlog.get_logger()
router = APIRouter()

# Initialize retrieval service
retrieval_service = GraphRAGRetrieval()


@router.post(
    "/past-defenses",
    response_model=RetrievalResponse,
    summary="Retrieve past defenses",
    description="Retrieve past legal defenses using GraphRAG hybrid search",
)
async def retrieve_past_defenses(request: RetrievalRequest) -> RetrievalResponse:
    """Retrieve past defenses for given criteria.
    
    Args:
        request: Retrieval request with search parameters
        
    Returns:
        Response with ranked argument bundles
        
    Raises:
        HTTPException: If retrieval fails
    """
    try:
        logger.info(
            "Retrieving past defenses",
            lawyer_id=request.lawyer_id,
            issue_id=request.current_issue_id,
            jurisdiction=request.jurisdiction,
        )
        
        response = await retrieval_service.retrieve_past_defenses(request)
        
        if not response.bundles:
            logger.warning("No past defenses found", request=request.dict())
            
        return response
        
    except ValueError as e:
        logger.error(f"Invalid request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error retrieving past defenses: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve past defenses",
        )


@router.get(
    "/search",
    response_model=RetrievalResponse,
    summary="Search arguments",
    description="Search for legal arguments with filters",
)
async def search_arguments(
    lawyer_id: Optional[str] = None,
    issue_id: Optional[str] = None,
    issue_text: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    judge_id: Optional[str] = None,
    limit: int = 10,
) -> RetrievalResponse:
    """Search for legal arguments.
    
    Args:
        lawyer_id: Lawyer identifier
        issue_id: Issue identifier
        issue_text: Issue description text
        jurisdiction: Jurisdiction code
        judge_id: Judge identifier
        limit: Maximum results
        
    Returns:
        Response with search results
        
    Raises:
        HTTPException: If search fails
    """
    try:
        # Build request
        request = RetrievalRequest(
            lawyer_id=lawyer_id,
            current_issue_id=issue_id,
            issue_text=issue_text,
            jurisdiction=jurisdiction,
            judge_id=judge_id,
            limit=limit,
        )
        
        response = await retrieval_service.retrieve_past_defenses(request)
        return response
        
    except ValueError as e:
        logger.error(f"Invalid search parameters: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error searching arguments: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed",
        )