"""
API endpoints for legal data retrieval from external sources.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import structlog

from ..services.legal_data_apis import (
    LegalDataAPIClient,
    GraphRAGIntegration,
    DataSource,
    LegalCase,
    LegalDocument
)
from ..db.graph_db import GraphDB
from ..db.vector_db import VectorDB

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/legal-data", tags=["legal-data"])


class CaseSearchRequest(BaseModel):
    """Request model for case search."""
    query: str = Field(..., description="Search query text")
    sources: Optional[List[str]] = Field(
        None,
        description="Data sources to search (courtlistener, cap, etc.)"
    )
    jurisdiction: Optional[str] = Field(None, description="Jurisdiction filter")
    date_from: Optional[datetime] = Field(None, description="Start date filter")
    date_to: Optional[datetime] = Field(None, description="End date filter")
    limit: int = Field(10, ge=1, le=100, description="Maximum results")


class RegulationSearchRequest(BaseModel):
    """Request model for regulation search."""
    query: str = Field(..., description="Search query text")
    agency: Optional[str] = Field(None, description="Agency filter")
    date_from: Optional[datetime] = Field(None, description="Effective date filter")
    limit: int = Field(10, ge=1, le=100, description="Maximum results")


class StateLegislationRequest(BaseModel):
    """Request model for state legislation search."""
    state: str = Field(..., description="State abbreviation (e.g., CA, NY)")
    query: Optional[str] = Field(None, description="Search query")
    session: Optional[str] = Field(None, description="Legislative session")
    limit: int = Field(10, ge=1, le=100, description="Maximum results")


class ImportRequest(BaseModel):
    """Request model for importing cases to GraphRAG."""
    query: str = Field(..., description="Search query for cases to import")
    sources: Optional[List[str]] = Field(None, description="Data sources to use")
    limit: int = Field(100, ge=1, le=1000, description="Maximum cases to import")


class SearchResponse(BaseModel):
    """Response model for search results."""
    results: List[dict]
    total_count: int
    query: str
    sources: List[str]
    execution_time_ms: int


# Dependency to get API client
async def get_api_client():
    """Get legal data API client instance."""
    return LegalDataAPIClient()


# Dependency to get GraphRAG integration
async def get_graphrag_integration():
    """Get GraphRAG integration instance."""
    client = LegalDataAPIClient()
    graph_db = GraphDB()
    vector_db = VectorDB()
    return GraphRAGIntegration(client, graph_db, vector_db)


@router.post("/search/cases", response_model=SearchResponse)
async def search_cases(
    request: CaseSearchRequest,
    client: LegalDataAPIClient = Depends(get_api_client)
):
    """
    Search for legal cases across multiple data sources.
    
    Supported sources:
    - courtlistener: CourtListener (federal and state cases)
    - cap: Caselaw Access Project (historical cases)
    """
    import time
    start_time = time.time()
    
    try:
        # Convert string sources to DataSource enum
        sources = None
        if request.sources:
            sources = []
            for source_str in request.sources:
                try:
                    sources.append(DataSource(source_str.lower()))
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid source: {source_str}"
                    )
        
        # Search cases
        cases = await client.search_cases(
            query=request.query,
            sources=sources,
            jurisdiction=request.jurisdiction,
            date_from=request.date_from,
            date_to=request.date_to,
            limit=request.limit
        )
        
        # Convert to response format
        results = []
        for case in cases:
            results.append(case.dict())
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        return SearchResponse(
            results=results,
            total_count=len(results),
            query=request.query,
            sources=[s.value for s in (sources or [DataSource.COURTLISTENER, DataSource.CAP])],
            execution_time_ms=execution_time_ms
        )
        
    except Exception as e:
        logger.error(f"Error searching cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/regulations", response_model=SearchResponse)
async def search_regulations(
    request: RegulationSearchRequest,
    client: LegalDataAPIClient = Depends(get_api_client)
):
    """
    Search for federal regulations and government documents.
    
    Sources:
    - govinfo: GovInfo (federal documents)
    - ecfr: Electronic Code of Federal Regulations
    """
    import time
    start_time = time.time()
    
    try:
        # Search regulations
        documents = await client.get_regulations(
            query=request.query,
            agency=request.agency,
            date_from=request.date_from,
            limit=request.limit
        )
        
        # Convert to response format
        results = []
        for doc in documents:
            results.append(doc.dict())
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        return SearchResponse(
            results=results,
            total_count=len(results),
            query=request.query,
            sources=["govinfo", "ecfr"],
            execution_time_ms=execution_time_ms
        )
        
    except Exception as e:
        logger.error(f"Error searching regulations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/state-legislation", response_model=SearchResponse)
async def search_state_legislation(
    request: StateLegislationRequest,
    client: LegalDataAPIClient = Depends(get_api_client)
):
    """
    Search for state legislation and bills.
    
    Source: OpenStates
    """
    import time
    start_time = time.time()
    
    try:
        # Search state legislation
        documents = await client.get_state_legislation(
            state=request.state,
            query=request.query,
            session=request.session,
            limit=request.limit
        )
        
        # Convert to response format
        results = []
        for doc in documents:
            results.append(doc.dict())
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        return SearchResponse(
            results=results,
            total_count=len(results),
            query=request.query or f"All bills in {request.state}",
            sources=["openstates"],
            execution_time_ms=execution_time_ms
        )
        
    except Exception as e:
        logger.error(f"Error searching state legislation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/cases")
async def import_cases_to_graphrag(
    request: ImportRequest,
    integration: GraphRAGIntegration = Depends(get_graphrag_integration)
):
    """
    Import legal cases into GraphRAG system.
    
    This endpoint:
    1. Searches for cases using external APIs
    2. Creates nodes in Neo4j graph database
    3. Indexes text in vector database
    4. Creates citation relationships
    """
    try:
        # Convert string sources to DataSource enum
        sources = None
        if request.sources:
            sources = []
            for source_str in request.sources:
                try:
                    sources.append(DataSource(source_str.lower()))
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid source: {source_str}"
                    )
        
        # Import cases
        imported_count = await integration.import_cases_to_graph(
            query=request.query,
            sources=sources,
            limit=request.limit
        )
        
        return {
            "success": True,
            "imported_count": imported_count,
            "query": request.query,
            "message": f"Successfully imported {imported_count} cases to GraphRAG"
        }
        
    except Exception as e:
        logger.error(f"Error importing cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources")
async def get_available_sources():
    """Get list of available legal data sources."""
    sources = []
    for source in DataSource:
        sources.append({
            "id": source.value,
            "name": source.name,
            "description": get_source_description(source)
        })
    
    return {"sources": sources}


def get_source_description(source: DataSource) -> str:
    """Get description for a data source."""
    descriptions = {
        DataSource.COURTLISTENER: "Federal and state court cases with PACER data",
        DataSource.RECAP: "Federal court electronic records archive",
        DataSource.CAP: "Historical U.S. case law from Harvard (1658-2020)",
        DataSource.GOVINFO: "Federal government documents and publications",
        DataSource.ECFR: "Electronic Code of Federal Regulations",
        DataSource.OYEZ: "Supreme Court audio and case information",
        DataSource.OPENSTATES: "State legislation and bill tracking"
    }
    return descriptions.get(source, "Legal data source")


@router.get("/health")
async def health_check(client: LegalDataAPIClient = Depends(get_api_client)):
    """Check health status of legal data APIs."""
    status = {}
    
    # Check each API availability
    for source in DataSource:
        config = client.configs[source]
        status[source.value] = {
            "configured": bool(not config.requires_auth or config.api_key),
            "base_url": config.base_url,
            "rate_limit": config.rate_limit
        }
    
    return {
        "status": "healthy",
        "apis": status
    }