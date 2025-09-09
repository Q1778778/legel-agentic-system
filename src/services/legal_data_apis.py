"""
Legal Data API Integration Service

This module provides unified access to multiple legal data sources including:
- CourtListener (court cases and PACER data)
- RECAP (federal court electronic records)
- Caselaw Access Project (historical cases)
- GovInfo (federal regulations and documents)
- eCFR (electronic Code of Federal Regulations)
- Oyez (Supreme Court audio and cases) - optional
- OpenStates (state legislation) - optional
"""

import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
import aiohttp
import structlog
from pydantic import BaseModel, Field
import os
from urllib.parse import urlencode, quote

logger = structlog.get_logger()


class DataSource(Enum):
    """Available legal data sources."""
    COURTLISTENER = "courtlistener"
    RECAP = "recap"
    CAP = "caselaw_access_project"
    GOVINFO = "govinfo"
    ECFR = "ecfr"
    OYEZ = "oyez"
    OPENSTATES = "openstates"


class APIConfig(BaseModel):
    """Configuration for each API."""
    base_url: str
    api_key: Optional[str] = None
    rate_limit: int = 5000  # requests per hour
    auth_header: str = "Authorization"
    auth_prefix: str = "Token"
    requires_auth: bool = True
    timeout: int = 30


class LegalCase(BaseModel):
    """Standardized legal case model."""
    case_id: str
    source: DataSource
    caption: str
    court: str
    jurisdiction: Optional[str] = None
    filed_date: Optional[datetime] = None
    decided_date: Optional[datetime] = None
    docket_number: Optional[str] = None
    judges: List[str] = Field(default_factory=list)
    parties: Dict[str, List[str]] = Field(default_factory=dict)
    citations: List[str] = Field(default_factory=list)
    opinion_text: Optional[str] = None
    summary: Optional[str] = None
    precedents: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LegalDocument(BaseModel):
    """Standardized legal document model."""
    doc_id: str
    source: DataSource
    title: str
    doc_type: str  # regulation, statute, brief, etc.
    agency: Optional[str] = None
    effective_date: Optional[datetime] = None
    text: Optional[str] = None
    url: Optional[str] = None
    citations: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LegalDataAPIClient:
    """Unified client for accessing multiple legal data APIs."""
    
    def __init__(self):
        """Initialize the legal data API client."""
        # API configurations
        self.configs = {
            DataSource.COURTLISTENER: APIConfig(
                base_url="https://www.courtlistener.com/api/rest/v4",
                api_key=os.getenv("COURTLISTENER_API_KEY"),
                rate_limit=5000,
                auth_header="Authorization",
                auth_prefix="Token",
                requires_auth=True
            ),
            DataSource.RECAP: APIConfig(
                base_url="https://www.courtlistener.com/api/rest/v4/recap",
                api_key=os.getenv("COURTLISTENER_API_KEY"),  # Uses same key
                rate_limit=5000,
                requires_auth=True
            ),
            DataSource.CAP: APIConfig(
                base_url="https://api.case.law/v1",
                api_key=os.getenv("CAP_API_KEY"),
                rate_limit=500,
                requires_auth=False  # Now freely available
            ),
            DataSource.GOVINFO: APIConfig(
                base_url="https://api.govinfo.gov",
                api_key=os.getenv("GOVINFO_API_KEY"),
                rate_limit=1000,
                auth_header="X-Api-Key",
                auth_prefix="",
                requires_auth=True
            ),
            DataSource.ECFR: APIConfig(
                base_url="https://www.ecfr.gov/api/v1",
                requires_auth=False,
                rate_limit=1000
            ),
            DataSource.OYEZ: APIConfig(
                base_url="https://api.oyez.org",
                requires_auth=False,
                rate_limit=1000
            ),
            DataSource.OPENSTATES: APIConfig(
                base_url="https://v3.openstates.org",
                api_key=os.getenv("OPENSTATES_API_KEY"),
                auth_header="X-API-KEY",
                auth_prefix="",
                requires_auth=True,
                rate_limit=1000
            )
        }
        
        # Rate limiting tracking
        self.request_counts = {}
        self.request_windows = {}
        
        # Cache for frequently accessed data
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour
        
    async def search_cases(
        self,
        query: str,
        sources: Optional[List[DataSource]] = None,
        jurisdiction: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 10
    ) -> List[LegalCase]:
        """
        Search for legal cases across multiple sources.
        
        Args:
            query: Search query text
            sources: List of data sources to search (None = all)
            jurisdiction: Filter by jurisdiction
            date_from: Start date filter
            date_to: End date filter
            limit: Maximum results per source
            
        Returns:
            List of standardized legal cases
        """
        if sources is None:
            sources = [DataSource.COURTLISTENER, DataSource.CAP]
        
        tasks = []
        for source in sources:
            if source == DataSource.COURTLISTENER:
                tasks.append(self._search_courtlistener(
                    query, jurisdiction, date_from, date_to, limit
                ))
            elif source == DataSource.CAP:
                tasks.append(self._search_cap(
                    query, jurisdiction, date_from, date_to, limit
                ))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten results and handle errors
        cases = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error searching cases: {result}")
            elif isinstance(result, list):
                cases.extend(result)
        
        return cases
    
    async def _search_courtlistener(
        self,
        query: str,
        jurisdiction: Optional[str],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        limit: int
    ) -> List[LegalCase]:
        """Search CourtListener for cases."""
        cases = []
        
        # Check cache first
        cache_key = self._get_cache_key("courtlistener", query, jurisdiction, date_from, date_to)
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if datetime.now().timestamp() - cached_time < self.cache_ttl:
                logger.info("Using cached CourtListener data")
                return cached_data[:limit]
        
        try:
            # Build search parameters
            params = {
                "q": query,
                "type": "o",  # opinions
                "order_by": "score desc",
                "page_size": min(limit, 100)
            }
            
            if jurisdiction:
                params["court"] = jurisdiction
            
            if date_from:
                params["filed_after"] = date_from.strftime("%Y-%m-%d")
            
            if date_to:
                params["filed_before"] = date_to.strftime("%Y-%m-%d")
            
            # Make API request
            url = f"{self.configs[DataSource.COURTLISTENER].base_url}/search/"
            headers = self._get_auth_headers(DataSource.COURTLISTENER)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Parse results
                        for item in data.get("results", [])[:limit]:
                            case = self._parse_courtlistener_case(item)
                            if case:
                                cases.append(case)
                        
                        # Cache results
                        self.cache[cache_key] = (cases, datetime.now().timestamp())
                    else:
                        logger.error(f"CourtListener API error: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error searching CourtListener: {e}")
        
        return cases
    
    async def _search_cap(
        self,
        query: str,
        jurisdiction: Optional[str],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        limit: int
    ) -> List[LegalCase]:
        """Search Caselaw Access Project for cases."""
        cases = []
        
        # Check cache first
        cache_key = self._get_cache_key("cap", query, jurisdiction, date_from, date_to)
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if datetime.now().timestamp() - cached_time < self.cache_ttl:
                logger.info("Using cached CAP data")
                return cached_data[:limit]
        
        try:
            # Build search parameters
            params = {
                "search": query,
                "page_size": min(limit, 100)
            }
            
            if jurisdiction:
                params["jurisdiction"] = jurisdiction
            
            if date_from:
                params["decision_date_min"] = date_from.strftime("%Y-%m-%d")
            
            if date_to:
                params["decision_date_max"] = date_to.strftime("%Y-%m-%d")
            
            # Make API request
            url = f"{self.configs[DataSource.CAP].base_url}/cases/"
            headers = self._get_auth_headers(DataSource.CAP)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Parse results
                        for item in data.get("results", [])[:limit]:
                            case = self._parse_cap_case(item)
                            if case:
                                cases.append(case)
                        
                        # Cache results
                        self.cache[cache_key] = (cases, datetime.now().timestamp())
                    else:
                        logger.error(f"CAP API error: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error searching CAP: {e}")
        
        return cases
    
    async def get_regulations(
        self,
        query: str,
        agency: Optional[str] = None,
        date_from: Optional[datetime] = None,
        limit: int = 10
    ) -> List[LegalDocument]:
        """
        Search for federal regulations.
        
        Args:
            query: Search query
            agency: Filter by agency
            date_from: Effective date filter
            limit: Maximum results
            
        Returns:
            List of legal documents
        """
        documents = []
        
        # Search GovInfo
        govinfo_docs = await self._search_govinfo(query, agency, date_from, limit)
        documents.extend(govinfo_docs)
        
        # Search eCFR
        ecfr_docs = await self._search_ecfr(query, limit)
        documents.extend(ecfr_docs)
        
        return documents[:limit]
    
    async def _search_govinfo(
        self,
        query: str,
        agency: Optional[str],
        date_from: Optional[datetime],
        limit: int
    ) -> List[LegalDocument]:
        """Search GovInfo for federal documents."""
        documents = []
        
        try:
            # Build search parameters
            params = {
                "query": query,
                "pageSize": min(limit, 100),
                "offsetMark": "*"
            }
            
            if agency:
                params["publishedBy"] = agency
            
            if date_from:
                params["publishedDate"] = f"[{date_from.strftime('%Y-%m-%d')} TO *]"
            
            # Make API request
            url = f"{self.configs[DataSource.GOVINFO].base_url}/search"
            headers = self._get_auth_headers(DataSource.GOVINFO)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Parse results
                        for item in data.get("results", [])[:limit]:
                            doc = self._parse_govinfo_document(item)
                            if doc:
                                documents.append(doc)
                    else:
                        logger.error(f"GovInfo API error: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error searching GovInfo: {e}")
        
        return documents
    
    async def _search_ecfr(
        self,
        query: str,
        limit: int
    ) -> List[LegalDocument]:
        """Search eCFR for federal regulations."""
        documents = []
        
        try:
            # Build search URL
            params = {
                "q": query,
                "per_page": min(limit, 100)
            }
            
            url = f"{self.configs[DataSource.ECFR].base_url}/search"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Parse results
                        for item in data.get("results", [])[:limit]:
                            doc = self._parse_ecfr_document(item)
                            if doc:
                                documents.append(doc)
                    else:
                        logger.error(f"eCFR API error: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error searching eCFR: {e}")
        
        return documents
    
    async def get_state_legislation(
        self,
        state: str,
        query: Optional[str] = None,
        session: Optional[str] = None,
        limit: int = 10
    ) -> List[LegalDocument]:
        """
        Get state legislation data.
        
        Args:
            state: State abbreviation (e.g., "CA", "NY")
            query: Optional search query
            session: Legislative session
            limit: Maximum results
            
        Returns:
            List of legal documents
        """
        documents = []
        
        try:
            # Build request parameters
            params = {
                "jurisdiction": state.lower(),
                "page_size": min(limit, 100)
            }
            
            if query:
                params["q"] = query
            
            if session:
                params["session"] = session
            
            # Make API request
            url = f"{self.configs[DataSource.OPENSTATES].base_url}/bills"
            headers = self._get_auth_headers(DataSource.OPENSTATES)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Parse results
                        for item in data.get("results", [])[:limit]:
                            doc = self._parse_openstates_bill(item)
                            if doc:
                                documents.append(doc)
                    else:
                        logger.error(f"OpenStates API error: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error searching OpenStates: {e}")
        
        return documents
    
    def _get_auth_headers(self, source: DataSource) -> Dict[str, str]:
        """Get authentication headers for API."""
        config = self.configs[source]
        headers = {"Accept": "application/json"}
        
        if config.requires_auth and config.api_key:
            if config.auth_prefix:
                headers[config.auth_header] = f"{config.auth_prefix} {config.api_key}"
            else:
                headers[config.auth_header] = config.api_key
        
        return headers
    
    def _get_cache_key(self, source: str, *args) -> str:
        """Generate cache key from arguments."""
        key_data = f"{source}:{':'.join(str(arg) for arg in args if arg)}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _parse_courtlistener_case(self, data: Dict[str, Any]) -> Optional[LegalCase]:
        """Parse CourtListener case data."""
        try:
            return LegalCase(
                case_id=f"cl_{data.get('id', '')}",
                source=DataSource.COURTLISTENER,
                caption=data.get("caseName", "Unknown Case"),
                court=data.get("court", {}).get("full_name", "Unknown Court"),
                jurisdiction=data.get("court", {}).get("jurisdiction", ""),
                filed_date=self._parse_date(data.get("dateFiled")),
                decided_date=self._parse_date(data.get("dateDecided")),
                docket_number=data.get("docketNumber", ""),
                judges=[j.get("name", "") for j in data.get("panel", [])],
                citations=data.get("citation", []),
                opinion_text=data.get("snippet", ""),
                metadata={
                    "absolute_url": data.get("absolute_url", ""),
                    "court_id": data.get("court_id", ""),
                    "status": data.get("status", "")
                }
            )
        except Exception as e:
            logger.error(f"Error parsing CourtListener case: {e}")
            return None
    
    def _parse_cap_case(self, data: Dict[str, Any]) -> Optional[LegalCase]:
        """Parse CAP case data."""
        try:
            return LegalCase(
                case_id=f"cap_{data.get('id', '')}",
                source=DataSource.CAP,
                caption=data.get("name", "Unknown Case"),
                court=data.get("court", {}).get("name", "Unknown Court"),
                jurisdiction=data.get("jurisdiction", {}).get("name", ""),
                decided_date=self._parse_date(data.get("decision_date")),
                docket_number=data.get("docket_number", ""),
                citations=[c.get("cite", "") for c in data.get("citations", [])],
                opinion_text=data.get("preview", ""),
                metadata={
                    "frontend_url": data.get("frontend_url", ""),
                    "volume": data.get("volume", {}).get("volume_number", ""),
                    "reporter": data.get("reporter", {}).get("full_name", "")
                }
            )
        except Exception as e:
            logger.error(f"Error parsing CAP case: {e}")
            return None
    
    def _parse_govinfo_document(self, data: Dict[str, Any]) -> Optional[LegalDocument]:
        """Parse GovInfo document data."""
        try:
            return LegalDocument(
                doc_id=f"govinfo_{data.get('packageId', '')}",
                source=DataSource.GOVINFO,
                title=data.get("title", "Unknown Document"),
                doc_type=data.get("collectionCode", "document"),
                agency=data.get("governmentAuthor", [""])[0] if data.get("governmentAuthor") else None,
                effective_date=self._parse_date(data.get("dateIssued")),
                url=data.get("pdfLink", ""),
                metadata={
                    "package_id": data.get("packageId", ""),
                    "collection": data.get("collectionName", ""),
                    "granule_id": data.get("granuleId", "")
                }
            )
        except Exception as e:
            logger.error(f"Error parsing GovInfo document: {e}")
            return None
    
    def _parse_ecfr_document(self, data: Dict[str, Any]) -> Optional[LegalDocument]:
        """Parse eCFR document data."""
        try:
            return LegalDocument(
                doc_id=f"ecfr_{data.get('section_number', '')}",
                source=DataSource.ECFR,
                title=data.get("title", "Unknown Regulation"),
                doc_type="regulation",
                text=data.get("text", ""),
                citations=[data.get("citation", "")],
                metadata={
                    "title_number": data.get("title_number", ""),
                    "part_number": data.get("part_number", ""),
                    "section_number": data.get("section_number", "")
                }
            )
        except Exception as e:
            logger.error(f"Error parsing eCFR document: {e}")
            return None
    
    def _parse_openstates_bill(self, data: Dict[str, Any]) -> Optional[LegalDocument]:
        """Parse OpenStates bill data."""
        try:
            return LegalDocument(
                doc_id=f"os_{data.get('id', '')}",
                source=DataSource.OPENSTATES,
                title=data.get("title", "Unknown Bill"),
                doc_type="legislation",
                text=data.get("latest_version", {}).get("note", ""),
                url=data.get("openstates_url", ""),
                metadata={
                    "identifier": data.get("identifier", ""),
                    "session": data.get("legislative_session", {}).get("identifier", ""),
                    "classification": data.get("classification", []),
                    "subject": data.get("subject", [])
                }
            )
        except Exception as e:
            logger.error(f"Error parsing OpenStates bill: {e}")
            return None
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime."""
        if not date_str:
            return None
        
        try:
            # Try common date formats
            for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"]:
                try:
                    return datetime.strptime(date_str[:len(fmt)], fmt)
                except:
                    continue
            return None
        except:
            return None


class GraphRAGIntegration:
    """Integration layer for legal data APIs with GraphRAG."""
    
    def __init__(self, api_client: LegalDataAPIClient, graph_db, vector_db):
        """
        Initialize GraphRAG integration.
        
        Args:
            api_client: Legal data API client
            graph_db: Neo4j graph database instance
            vector_db: Vector database instance
        """
        self.api_client = api_client
        self.graph_db = graph_db
        self.vector_db = vector_db
        
    async def import_cases_to_graph(
        self,
        query: str,
        sources: Optional[List[DataSource]] = None,
        limit: int = 100
    ) -> int:
        """
        Import legal cases into Neo4j graph.
        
        Args:
            query: Search query for cases
            sources: Data sources to use
            limit: Maximum cases to import
            
        Returns:
            Number of cases imported
        """
        # Search for cases
        cases = await self.api_client.search_cases(query, sources=sources, limit=limit)
        
        imported = 0
        for case in cases:
            try:
                # Create case node
                await self._create_case_node(case)
                
                # Create citation relationships
                await self._create_citation_relationships(case)
                
                # Index case text in vector database
                await self._index_case_text(case)
                
                imported += 1
                
            except Exception as e:
                logger.error(f"Error importing case {case.case_id}: {e}")
        
        logger.info(f"Imported {imported} cases to GraphRAG")
        return imported
    
    async def _create_case_node(self, case: LegalCase):
        """Create case node in Neo4j."""
        query = """
        MERGE (c:Case {case_id: $case_id})
        SET c.caption = $caption,
            c.court = $court,
            c.jurisdiction = $jurisdiction,
            c.filed_date = $filed_date,
            c.decided_date = $decided_date,
            c.docket_number = $docket_number,
            c.source = $source
        """
        
        params = {
            "case_id": case.case_id,
            "caption": case.caption,
            "court": case.court,
            "jurisdiction": case.jurisdiction,
            "filed_date": case.filed_date.isoformat() if case.filed_date else None,
            "decided_date": case.decided_date.isoformat() if case.decided_date else None,
            "docket_number": case.docket_number,
            "source": case.source.value
        }
        
        # Execute query (assuming graph_db has an execute method)
        # This would need to be implemented based on your Neo4j driver
        # await self.graph_db.execute(query, params)
    
    async def _create_citation_relationships(self, case: LegalCase):
        """Create citation relationships in graph."""
        for citation in case.citations:
            query = """
            MATCH (c1:Case {case_id: $case_id})
            MERGE (c2:Citation {cite: $citation})
            MERGE (c1)-[:CITES]->(c2)
            """
            
            params = {
                "case_id": case.case_id,
                "citation": citation
            }
            
            # Execute query
            # await self.graph_db.execute(query, params)
    
    async def _index_case_text(self, case: LegalCase):
        """Index case text in vector database."""
        if case.opinion_text:
            # Generate embedding (assuming you have an embedding service)
            # embedding = await self.embedding_service.embed_text(case.opinion_text)
            
            # Store in vector database
            metadata = {
                "case_id": case.case_id,
                "caption": case.caption,
                "court": case.court,
                "source": case.source.value
            }
            
            # await self.vector_db.add_vector(embedding, metadata)
    
    async def search_and_retrieve(
        self,
        query: str,
        use_graph: bool = True,
        use_vector: bool = True,
        sources: Optional[List[DataSource]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search and retrieve relevant legal data.
        
        Args:
            query: Search query
            use_graph: Use graph traversal
            use_vector: Use vector similarity
            sources: Data sources to search
            limit: Maximum results
            
        Returns:
            List of relevant legal documents/cases
        """
        results = []
        
        # Search external APIs
        api_cases = await self.api_client.search_cases(query, sources=sources, limit=limit)
        
        # Convert to result format
        for case in api_cases:
            results.append({
                "type": "case",
                "id": case.case_id,
                "caption": case.caption,
                "court": case.court,
                "relevance_score": 0.8,  # Would be calculated
                "source": case.source.value,
                "text": case.opinion_text or case.summary or ""
            })
        
        # If using graph, add graph results
        if use_graph:
            # Graph traversal logic here
            pass
        
        # If using vector, add vector search results
        if use_vector:
            # Vector search logic here
            pass
        
        # Sort by relevance score
        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        return results[:limit]


# Example usage
async def main():
    """Example usage of the legal data API client."""
    
    # Initialize client
    client = LegalDataAPIClient()
    
    # Search for patent cases
    patent_cases = await client.search_cases(
        query="patent infringement software",
        sources=[DataSource.COURTLISTENER, DataSource.CAP],
        limit=5
    )
    
    print(f"Found {len(patent_cases)} patent cases")
    for case in patent_cases:
        print(f"- {case.caption} ({case.court})")
    
    # Search for federal regulations
    regulations = await client.get_regulations(
        query="data privacy",
        limit=5
    )
    
    print(f"\nFound {len(regulations)} regulations")
    for reg in regulations:
        print(f"- {reg.title}")
    
    # Search state legislation
    state_bills = await client.get_state_legislation(
        state="CA",
        query="artificial intelligence",
        limit=5
    )
    
    print(f"\nFound {len(state_bills)} state bills")
    for bill in state_bills:
        print(f"- {bill.title}")


if __name__ == "__main__":
    asyncio.run(main())