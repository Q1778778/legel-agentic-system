"""
Integration module for connecting with downstream services.

This module handles data transformation and communication with
the info fetcher and GraphRAG backend.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import (
    ExtractedCaseInfo,
    Party,
    CourtInfo,
    LegalIssue,
    ReliefSought,
    DocumentReference,
    ExtractionSession
)
from .validators import CaseInfoValidator


logger = logging.getLogger(__name__)


class InfoFetcherIntegration:
    """Integration with the info fetcher service."""
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the integration."""
        self.config = config or {}
        self.base_url = self.config.get('info_fetcher_url', 'http://localhost:8080')
        self.api_key = self.config.get('api_key')
        self.timeout = self.config.get('timeout', 30)
        self.max_retries = self.config.get('max_retries', 3)
        
    async def send_case_info(
        self, 
        case_info: ExtractedCaseInfo,
        session_id: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Send extracted case information to the info fetcher.
        
        Args:
            case_info: The extracted case information
            session_id: Optional session identifier
            
        Returns:
            Tuple of (success, response_data)
        """
        # Validate before sending
        is_valid, errors, warnings = CaseInfoValidator.validate_for_integration(
            case_info, 
            'info_fetcher'
        )
        
        if not is_valid:
            logger.error(f"Validation failed: {errors}")
            return False, {'errors': errors, 'warnings': warnings}
        
        # Transform to fetcher format
        fetcher_data = self._transform_to_fetcher_format(case_info, session_id)
        
        # Send to info fetcher
        try:
            success, response = await self._send_request(fetcher_data)
            
            if success:
                logger.info(f"Successfully sent case info to fetcher: {case_info.case_number or case_info.case_title}")
            else:
                logger.error(f"Failed to send case info: {response}")
            
            return success, response
            
        except Exception as e:
            logger.error(f"Error sending to info fetcher: {e}")
            return False, {'error': str(e)}
    
    async def send_batch(
        self, 
        case_infos: List[ExtractedCaseInfo]
    ) -> List[Tuple[bool, Dict[str, Any]]]:
        """
        Send multiple case infos in batch.
        
        Args:
            case_infos: List of extracted case information
            
        Returns:
            List of (success, response_data) tuples
        """
        tasks = [
            self.send_case_info(case_info, f"batch_{i}")
            for i, case_info in enumerate(case_infos)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append((False, {'error': str(result)}))
            else:
                processed_results.append(result)
        
        return processed_results
    
    def _transform_to_fetcher_format(
        self, 
        case_info: ExtractedCaseInfo,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Transform ExtractedCaseInfo to info fetcher format."""
        # Build parties list
        parties_data = []
        for party in case_info.parties:
            party_data = {
                'name': party.name,
                'type': party.party_type.value,
                'attorneys': party.attorneys or [],
            }
            if party.contact_info:
                party_data['contact'] = party.contact_info
            if party.role_description:
                party_data['role'] = party.role_description
            parties_data.append(party_data)
        
        # Build court data
        court_data = None
        if case_info.court_info:
            court_data = {
                'name': case_info.court_info.name,
                'jurisdiction': case_info.court_info.jurisdiction,
                'location': case_info.court_info.location,
                'judge': case_info.court_info.judge,
                'department': case_info.court_info.department,
            }
        
        # Build legal issues
        issues_data = []
        claims_data = []
        defenses_data = []
        
        for issue in case_info.legal_issues:
            issues_data.append({
                'description': issue.issue,
                'category': issue.category,
                'isPrimary': issue.is_primary
            })
            
            if issue.related_claims:
                claims_data.extend(issue.related_claims)
            if issue.related_defenses:
                defenses_data.extend(issue.related_defenses)
        
        # Build relief data
        relief_data = None
        if case_info.relief_sought:
            relief_data = {
                'monetary': case_info.relief_sought.monetary_damages,
                'injunctive': case_info.relief_sought.injunctive_relief,
                'declaratory': case_info.relief_sought.declaratory_relief,
                'other': case_info.relief_sought.other_relief or []
            }
        
        # Build citations
        citations_data = {
            'cases': [],
            'statutes': [],
            'regulations': [],
            'rules': []
        }
        
        for ref in case_info.document_references:
            citation_item = {
                'citation': ref.citation,
                'title': ref.title,
                'relevance': ref.relevance
            }
            
            if ref.reference_type == 'case':
                citations_data['cases'].append(citation_item)
            elif ref.reference_type == 'statute':
                citations_data['statutes'].append(citation_item)
            elif ref.reference_type == 'regulation':
                citations_data['regulations'].append(citation_item)
            elif ref.reference_type == 'rule':
                citations_data['rules'].append(citation_item)
        
        # Build the complete payload
        fetcher_payload = {
            'metadata': {
                'sessionId': session_id,
                'extractionSource': case_info.extraction_source,
                'extractionTimestamp': case_info.extraction_timestamp.isoformat(),
                'confidenceScore': case_info.confidence_score,
                'documentType': case_info.document_type.value if case_info.document_type else None,
            },
            'caseInfo': {
                'caseNumber': case_info.case_number,
                'caseTitle': case_info.case_title,
                'filingDate': case_info.filing_date.isoformat() if case_info.filing_date else None,
                'caseType': case_info.case_type.value if case_info.case_type else None,
                'caseStage': case_info.case_stage.value if case_info.case_stage else None,
            },
            'parties': parties_data,
            'court': court_data,
            'legalContext': {
                'issues': issues_data,
                'claims': claims_data,
                'defenses': defenses_data,
            },
            'facts': {
                'summary': case_info.fact_summary,
                'disputed': case_info.disputed_facts or [],
            },
            'relief': relief_data,
            'citations': citations_data,
            'additionalInfo': case_info.additional_info,
        }
        
        return fetcher_payload
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _send_request(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Send HTTP request to info fetcher with retry logic."""
        headers = {
            'Content-Type': 'application/json',
        }
        
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.base_url}/api/case-info",
                    json=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    response_data = await response.json()
                    
                    if response.status == 200:
                        return True, response_data
                    else:
                        return False, {
                            'status': response.status,
                            'error': response_data.get('error', 'Unknown error'),
                            'details': response_data
                        }
                        
            except asyncio.TimeoutError:
                logger.error("Request timed out")
                raise
            except aiohttp.ClientError as e:
                logger.error(f"Client error: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                raise


class GraphRAGIntegration:
    """Integration with GraphRAG backend."""
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the GraphRAG integration."""
        self.config = config or {}
        self.base_url = self.config.get('graphrag_url', 'http://localhost:8081')
        self.api_key = self.config.get('api_key')
        
    async def query_similar_cases(
        self, 
        case_info: ExtractedCaseInfo,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query GraphRAG for similar cases.
        
        Args:
            case_info: The case to find similarities for
            limit: Maximum number of similar cases to return
            
        Returns:
            List of similar cases with relevance scores
        """
        # Build query from case info
        query_params = {
            'case_type': case_info.case_type.value if case_info.case_type else None,
            'legal_issues': [issue.issue for issue in case_info.legal_issues],
            'jurisdiction': case_info.court_info.jurisdiction if case_info.court_info else None,
            'limit': limit
        }
        
        headers = {
            'Content-Type': 'application/json',
        }
        
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.base_url}/api/similar-cases",
                    json=query_params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"GraphRAG query failed with status {response.status}")
                        return []
                        
            except Exception as e:
                logger.error(f"Error querying GraphRAG: {e}")
                return []
    
    async def store_case_graph(
        self, 
        case_info: ExtractedCaseInfo
    ) -> Tuple[bool, Optional[str]]:
        """
        Store case information in GraphRAG.
        
        Args:
            case_info: The case information to store
            
        Returns:
            Tuple of (success, graph_id)
        """
        # Transform to graph format
        graph_data = self._transform_to_graph_format(case_info)
        
        headers = {
            'Content-Type': 'application/json',
        }
        
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.base_url}/api/store-case",
                    json=graph_data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return True, result.get('graph_id')
                    else:
                        logger.error(f"Failed to store in GraphRAG: {response.status}")
                        return False, None
                        
            except Exception as e:
                logger.error(f"Error storing in GraphRAG: {e}")
                return False, None
    
    def _transform_to_graph_format(self, case_info: ExtractedCaseInfo) -> Dict[str, Any]:
        """Transform case info to graph storage format."""
        nodes = []
        edges = []
        
        # Create case node
        case_node = {
            'id': f"case_{case_info.case_number or 'unknown'}",
            'type': 'case',
            'properties': {
                'case_number': case_info.case_number,
                'case_title': case_info.case_title,
                'filing_date': case_info.filing_date.isoformat() if case_info.filing_date else None,
                'case_type': case_info.case_type.value if case_info.case_type else None,
                'case_stage': case_info.case_stage.value if case_info.case_stage else None,
                'confidence_score': case_info.confidence_score,
            }
        }
        nodes.append(case_node)
        
        # Create party nodes and edges
        for party in case_info.parties:
            party_node = {
                'id': f"party_{party.name.replace(' ', '_')}",
                'type': 'party',
                'properties': {
                    'name': party.name,
                    'party_type': party.party_type.value,
                    'attorneys': party.attorneys or []
                }
            }
            nodes.append(party_node)
            
            # Create edge from party to case
            edge = {
                'source': party_node['id'],
                'target': case_node['id'],
                'type': 'involved_in',
                'properties': {
                    'role': party.party_type.value
                }
            }
            edges.append(edge)
        
        # Create court node and edge
        if case_info.court_info:
            court_node = {
                'id': f"court_{case_info.court_info.name.replace(' ', '_')}",
                'type': 'court',
                'properties': {
                    'name': case_info.court_info.name,
                    'jurisdiction': case_info.court_info.jurisdiction,
                    'judge': case_info.court_info.judge
                }
            }
            nodes.append(court_node)
            
            edge = {
                'source': case_node['id'],
                'target': court_node['id'],
                'type': 'filed_in',
                'properties': {}
            }
            edges.append(edge)
        
        # Create legal issue nodes
        for issue in case_info.legal_issues:
            issue_node = {
                'id': f"issue_{issue.category}_{hash(issue.issue) % 1000}",
                'type': 'legal_issue',
                'properties': {
                    'description': issue.issue,
                    'category': issue.category,
                    'is_primary': issue.is_primary
                }
            }
            nodes.append(issue_node)
            
            edge = {
                'source': case_node['id'],
                'target': issue_node['id'],
                'type': 'involves',
                'properties': {
                    'is_primary': issue.is_primary
                }
            }
            edges.append(edge)
        
        return {
            'nodes': nodes,
            'edges': edges,
            'metadata': {
                'extraction_source': case_info.extraction_source,
                'extraction_timestamp': case_info.extraction_timestamp.isoformat(),
                'document_type': case_info.document_type.value if case_info.document_type else None
            }
        }


class IntegrationManager:
    """Manager for all integrations."""
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the integration manager."""
        self.config = config or {}
        self.info_fetcher = InfoFetcherIntegration(
            self.config.get('info_fetcher', {})
        )
        self.graphrag = GraphRAGIntegration(
            self.config.get('graphrag', {})
        )
        
    async def process_extraction(
        self, 
        case_info: ExtractedCaseInfo,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process extracted case info through all integrations.
        
        Args:
            case_info: The extracted case information
            session_id: Optional session identifier
            
        Returns:
            Dictionary with results from all integrations
        """
        results = {
            'info_fetcher': None,
            'graphrag': None,
            'similar_cases': None,
            'errors': []
        }
        
        # Send to info fetcher
        try:
            success, response = await self.info_fetcher.send_case_info(
                case_info, 
                session_id
            )
            results['info_fetcher'] = {
                'success': success,
                'response': response
            }
        except Exception as e:
            results['errors'].append(f"Info fetcher error: {str(e)}")
        
        # Store in GraphRAG
        try:
            success, graph_id = await self.graphrag.store_case_graph(case_info)
            results['graphrag'] = {
                'success': success,
                'graph_id': graph_id
            }
        except Exception as e:
            results['errors'].append(f"GraphRAG storage error: {str(e)}")
        
        # Query for similar cases
        try:
            similar_cases = await self.graphrag.query_similar_cases(case_info)
            results['similar_cases'] = similar_cases
        except Exception as e:
            results['errors'].append(f"Similar cases query error: {str(e)}")
        
        return results