"""
Metrics API endpoints for Court Argument Simulator
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any
from src.services.metrics import MetricsService
import structlog

logger = structlog.get_logger()
router = APIRouter()

# Initialize metrics service
metrics_service = MetricsService()

@router.get("/win-rate")
async def get_win_rate(
    lawyer_id: Optional[str] = Query(None, description="Filter by lawyer ID"),
    issue_id: Optional[str] = Query(None, description="Filter by issue ID"),
    jurisdiction: Optional[str] = Query(None, description="Filter by jurisdiction"),
    judge_name: Optional[str] = Query(None, description="Filter by judge name")
) -> Dict[str, Any]:
    """
    Calculate Win Rate / Outcome Success
    Formula: (granted + 0.5*partial) / total
    """
    try:
        result = metrics_service.calculate_win_rate(
            lawyer_id=lawyer_id,
            issue_id=issue_id,
            jurisdiction=jurisdiction,
            judge_name=judge_name
        )
        return result
    except Exception as e:
        logger.error("Error calculating win rate", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/judge-alignment/{lawyer_id}")
async def get_judge_alignment(
    lawyer_id: str,
    judge_name: Optional[str] = Query(None, description="Filter by specific judge")
) -> Dict[str, Any]:
    """
    Calculate Judge Alignment Rate for a lawyer
    Formula: aligned_outcomes / total_appearances_before_judge
    """
    try:
        result = metrics_service.calculate_judge_alignment_rate(
            lawyer_id=lawyer_id,
            judge_name=judge_name
        )
        return result
    except Exception as e:
        logger.error("Error calculating judge alignment", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/argument-diversity")
async def get_argument_diversity(
    lawyer_id: Optional[str] = Query(None, description="Filter by lawyer ID"),
    issue_id: Optional[str] = Query(None, description="Filter by issue ID"),
    jurisdiction: Optional[str] = Query(None, description="Filter by jurisdiction")
) -> Dict[str, Any]:
    """
    Calculate Argument Diversity
    Formula: countDistinct(signature_hash)
    """
    try:
        result = metrics_service.calculate_argument_diversity(
            lawyer_id=lawyer_id,
            issue_id=issue_id,
            jurisdiction=jurisdiction
        )
        return result
    except Exception as e:
        logger.error("Error calculating argument diversity", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/comprehensive")
async def get_comprehensive_metrics(
    lawyer_id: Optional[str] = Query(None, description="Filter by lawyer ID"),
    issue_id: Optional[str] = Query(None, description="Filter by issue ID"),
    jurisdiction: Optional[str] = Query(None, description="Filter by jurisdiction"),
    judge_name: Optional[str] = Query(None, description="Filter by judge name")
) -> Dict[str, Any]:
    """
    Get all core metrics in one call:
    - Win Rate / Outcome Success
    - Judge Alignment Rate (if lawyer_id provided)
    - Argument Diversity
    """
    try:
        result = metrics_service.get_comprehensive_metrics(
            lawyer_id=lawyer_id,
            issue_id=issue_id,
            jurisdiction=jurisdiction,
            judge_name=judge_name
        )
        return result
    except Exception as e:
        logger.error("Error getting comprehensive metrics", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))