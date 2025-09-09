"""Microsoft GraphRAG integration service for legal document retrieval."""

import os
import asyncio
from typing import List, Dict, Any, Optional
import structlog
import time
from pathlib import Path
from datetime import datetime, timedelta
import hashlib
import random

# Import GraphRAG components
import subprocess
import json

from ..models.schemas import (
    ArgumentBundle,
    RetrievalRequest, 
    RetrievalResponse,
    ConfidenceScore,
    GraphExplanation,
    ArgumentSegment,
    Case,
    Issue,
)
from .enhanced_mock_data import get_generator

logger = structlog.get_logger()


class MicrosoftGraphRAGService:
    """Service for using Microsoft's official GraphRAG for legal document retrieval."""
    
    def __init__(self, graphrag_data_dir: str = None):
        """Initialize Microsoft GraphRAG service.
        
        Args:
            graphrag_data_dir: Path to GraphRAG data directory with indexed data
        """
        if graphrag_data_dir is None:
            # Default to graphrag_data directory in project root
            project_root = Path(__file__).parent.parent.parent
            graphrag_data_dir = os.path.join(project_root, "graphrag_data")
            
        self.graphrag_data_dir = Path(graphrag_data_dir)
        self.output_dir = self.graphrag_data_dir / "output"
        
        # Verify the data directory exists and has been indexed
        if not self.output_dir.exists():
            raise ValueError(f"GraphRAG output directory not found: {self.output_dir}")
        
        logger.info(f"Initialized Microsoft GraphRAG service with data dir: {self.graphrag_data_dir}")
    
    async def retrieve_past_defenses(
        self,
        request: RetrievalRequest,
    ) -> RetrievalResponse:
        """Retrieve past defense arguments using Microsoft GraphRAG.
        
        Args:
            request: Retrieval request with issue text and filters
            
        Returns:
            Response with ranked argument bundles and explanations
        """
        start_time = time.time()
        
        try:
            logger.info(f"GraphRAG query: {request.issue_text[:100]}...")
            
            # Use both local and global search for comprehensive results
            local_results = await self._local_search(request.issue_text)
            global_results = await self._global_search(request.issue_text)
            
            # Convert GraphRAG results to our data model
            bundles = self._convert_to_argument_bundles(
                local_results, 
                global_results, 
                request
            )
            
            # Limit results as requested
            limited_bundles = bundles[:request.limit]
            
            # Generate explanations for how results were found
            explanations = self._generate_explanations(limited_bundles)
            
            query_time_ms = int((time.time() - start_time) * 1000)
            
            return RetrievalResponse(
                bundles=limited_bundles,
                total_count=len(limited_bundles),
                query_time_ms=query_time_ms,
                graph_explanations=explanations,
                metrics=None  # Could add GraphRAG-specific metrics here
            )
            
        except Exception as e:
            logger.error(f"Error in Microsoft GraphRAG retrieval: {e}")
            
            # Fallback to mock data for demo purposes
            return await self._fallback_mock_response(request, start_time)
    
    async def _local_search(self, query: str) -> str:
        """Perform GraphRAG local search using CLI.
        
        Args:
            query: Search query
            
        Returns:
            Search response text
        """
        try:
            # Execute GraphRAG local search via CLI
            # Note: Using python -m graphrag instead of just graphrag for better compatibility
            cmd = ["/usr/local/bin/python", "-m", "graphrag", "query", "--method", "local", "--query", query]
            
            logger.info(f"Executing GraphRAG local search: {' '.join(cmd[:5])}...")
            
            result = subprocess.run(
                cmd,
                cwd=self.graphrag_data_dir,
                capture_output=True,
                text=True,
                timeout=7,  # Quick timeout for fast fallback
                env={**os.environ, "PYTHONWARNINGS": "ignore"}  # Suppress warnings
            )
            
            if result.returncode == 0:
                # Parse the output to extract the response text
                output_lines = result.stdout.split('\n')
                # Find the response after the log lines
                response_started = False
                response_lines = []
                
                for line in output_lines:
                    # GraphRAG 2.5.0 outputs the response after this line
                    if 'Local Search Response:' in line or 'graphrag.cli.query - Local Search Response:' in line:
                        response_started = True
                        continue
                    if response_started:
                        # Stop at the next log line (if any)
                        if line.startswith('2025-') or line.startswith('2024-'):
                            break
                        response_lines.append(line)
                
                response = '\n'.join(response_lines).strip()
                if response:
                    logger.info(f"GraphRAG local search successful, response length: {len(response)}")
                    return response
                else:
                    logger.warning("GraphRAG local search returned empty response")
                    return ""
            else:
                logger.error(f"GraphRAG local search failed with code {result.returncode}")
                logger.error(f"stderr: {result.stderr[:500]}")  # Log first 500 chars of error
                return ""
                
        except subprocess.TimeoutExpired:
            logger.warning("GraphRAG local search timed out after 7 seconds, will fallback to Neo4j/Mock")
            return ""
        except FileNotFoundError:
            logger.error("GraphRAG command not found. Please ensure graphrag is installed: pip install graphrag")
            return ""
        except Exception as e:
            logger.error(f"Local search error: {type(e).__name__}: {e}")
            return ""
    
    async def _global_search(self, query: str) -> str:
        """Perform GraphRAG global search using CLI.
        
        Args:
            query: Search query
            
        Returns:
            Search response text
        """
        try:
            # Execute GraphRAG global search via CLI
            # Note: Using python -m graphrag instead of just graphrag for better compatibility
            cmd = ["/usr/local/bin/python", "-m", "graphrag", "query", "--method", "global", "--query", query]
            
            logger.info(f"Executing GraphRAG global search: {' '.join(cmd[:5])}...")
            
            result = subprocess.run(
                cmd,
                cwd=self.graphrag_data_dir,
                capture_output=True,
                text=True,
                timeout=7,  # Quick timeout for fast fallback
                env={**os.environ, "PYTHONWARNINGS": "ignore"}  # Suppress warnings
            )
            
            if result.returncode == 0:
                # Parse the output to extract the response text
                output_lines = result.stdout.split('\n')
                # Find the response after the log lines
                response_started = False
                response_lines = []
                
                for line in output_lines:
                    # GraphRAG 2.5.0 outputs the response after this line
                    if 'Global Search Response:' in line or 'graphrag.cli.query - Global Search Response:' in line:
                        response_started = True
                        continue
                    if response_started:
                        # Stop at the next log line (if any)
                        if line.startswith('2025-') or line.startswith('2024-'):
                            break
                        response_lines.append(line)
                
                response = '\n'.join(response_lines).strip()
                if response:
                    logger.info(f"GraphRAG global search successful, response length: {len(response)}")
                    return response
                else:
                    logger.warning("GraphRAG global search returned empty response")
                    return ""
            else:
                logger.error(f"GraphRAG global search failed with code {result.returncode}")
                logger.error(f"stderr: {result.stderr[:500]}")  # Log first 500 chars of error
                return ""
                
        except subprocess.TimeoutExpired:
            logger.warning("GraphRAG global search timed out after 7 seconds, will fallback to Neo4j/Mock")
            return ""
        except FileNotFoundError:
            logger.error("GraphRAG command not found. Please ensure graphrag is installed: pip install graphrag")
            return ""
        except Exception as e:
            logger.error(f"Global search error: {type(e).__name__}: {e}")
            return ""
    
    def _convert_to_argument_bundles(
        self,
        local_results: str,
        global_results: str,
        request: RetrievalRequest
    ) -> List[ArgumentBundle]:
        """Convert GraphRAG search results to ArgumentBundle objects.
        
        Args:
            local_results: Local search response text
            global_results: Global search response text
            request: Original request
            
        Returns:
            List of ArgumentBundle objects
        """
        bundles = []
        
        # For now, create bundles based on the search results
        # In a production system, you'd parse the GraphRAG output more sophisticatedly
        
        if local_results:
            bundle = self._create_bundle_from_text(
                local_results, 
                "local_search",
                request,
                confidence=0.85
            )
            bundles.append(bundle)
        
        if global_results and global_results != local_results:
            bundle = self._create_bundle_from_text(
                global_results,
                "global_search", 
                request,
                confidence=0.80
            )
            bundles.append(bundle)
            
        # If no results, generate mock data for demo
        if not bundles:
            bundles = self._generate_mock_bundles(request.issue_text, request.limit)
        
        return bundles
    
    def _extract_citations(self, text: str) -> List[str]:
        """Extract citations from text.
        
        Args:
            text: Text containing citations
            
        Returns:
            List of citation strings
        """
        import re
        citations = []
        
        # Look for patterns like [Source: ...] or [Data: ...]
        pattern = r'\[(?:Source|Data|Reports|Entities|Relationships):[^\]]+\]'
        matches = re.findall(pattern, text)
        citations.extend(matches)
        
        # Also look for case names
        case_pattern = r'(?:v\.|vs\.)\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*'
        case_matches = re.findall(case_pattern, text)
        for match in case_matches:
            citations.append(f"Case: {match}")
        
        return citations[:5]  # Limit to 5 citations
    
    def _create_bundle_from_text(
        self, 
        text: str, 
        source_type: str,
        request: RetrievalRequest,
        confidence: float
    ) -> ArgumentBundle:
        """Create an ArgumentBundle from GraphRAG response text.
        
        Args:
            text: Response text from GraphRAG
            source_type: Type of search (local/global)
            request: Original request
            confidence: Confidence score
            
        Returns:
            ArgumentBundle object
        """
        # Generate consistent ID based on content
        content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        bundle_id = f"graphrag_{source_type}_{content_hash}"
        
        # Parse the GraphRAG markdown response
        lines = text.split('\n')
        segments = []
        current_section = []
        section_count = 0
        
        for line in lines:
            # Skip empty lines and markdown headers
            if not line.strip() or line.startswith('#'):
                # Save current section if it has content
                if current_section and len(' '.join(current_section)) > 50:
                    segment_text = ' '.join(current_section)
                    # Remove markdown formatting and data references
                    segment_text = segment_text.replace('[Data:', '[Source:')
                    
                    segment = ArgumentSegment(
                        segment_id=f"{bundle_id}_seg_{section_count:02d}",
                        argument_id=bundle_id,
                        text=segment_text,
                        role="opening" if section_count == 0 else "rebuttal",  # Use valid role values
                        seq=section_count,
                        citations=self._extract_citations(segment_text)
                    )
                    segments.append(segment)
                    section_count += 1
                    current_section = []
                    
                    if section_count >= 5:  # Limit to 5 segments
                        break
            else:
                current_section.append(line.strip())
        
        # Create mock case info (in production, extract from graph data)
        case = Case(
            id=f"case_{content_hash}",
            caption=f"GraphRAG Analysis Case - {source_type.title()}",
            court="GraphRAG Knowledge Graph",
            jurisdiction=request.jurisdiction or "Multi-jurisdictional",
            filed_date=datetime.now() - timedelta(days=random.randint(30, 365))
        )
        
        issue = Issue(
            id=f"issue_{content_hash}",
            title=f"Legal Analysis: {request.issue_text[:50]}...",
            taxonomy_path=["Law", "GraphRAG Analysis", source_type.title()]
        )
        
        confidence_score = ConfidenceScore(
            value=confidence,
            features={
                "graphrag_relevance": confidence,
                "source_type": source_type,
                "content_length": len(text),
                "segments_count": len(segments)
            }
        )
        
        return ArgumentBundle(
            argument_id=bundle_id,
            confidence=confidence_score,
            case=case,
            issue=issue,
            segments=segments
        )
    
    def _generate_explanations(
        self, 
        bundles: List[ArgumentBundle]
    ) -> List[GraphExplanation]:
        """Generate explanations for how results were found.
        
        Args:
            bundles: Argument bundles
            
        Returns:
            List of graph explanations
        """
        explanations = []
        
        for bundle in bundles:
            source_type = "graphrag"
            
            explanation = GraphExplanation(
                argument_id=bundle.argument_id,
                paths=[{
                    "type": f"graphrag_{source_type}",
                    "nodes": ["Query", "GraphRAG_Index", "Legal_Entities", "Analysis"],
                    "confidence": bundle.confidence.value
                }],
                key_nodes=["Legal_Cases", "Entities", "Relationships", "Communities"],
                explanation_text=f"Found via Microsoft GraphRAG {source_type} search using knowledge graph analysis of legal documents",
                final_score=bundle.confidence.value
            )
            explanations.append(explanation)
        
        return explanations
    
    def _generate_mock_bundles(self, issue_text: str, limit: int) -> List[ArgumentBundle]:
        """Generate mock argument bundles when no results are found.
        Uses real legal cases from enhanced_mock_data module.
        
        Args:
            issue_text: Query text
            limit: Number of bundles to generate
            
        Returns:
            List of mock ArgumentBundles
        """
        # Use the enhanced mock data generator with real legal cases
        generator = get_generator()
        
        # Generate argument bundles based on the query using real legal cases
        bundles_data = generator.generate_argument_bundles(issue_text, limit)
        
        # Convert to ArgumentBundle objects
        bundles = []
        for data in bundles_data:
            # The data already has the correct structure from enhanced_mock_data
            bundle = ArgumentBundle(
                argument_id=data["argument_id"],
                confidence=data["confidence"],
                case=data["case"],
                issue=data["issue"],
                segments=data["segments"]
            )
            bundles.append(bundle)
        
        logger.info(f"Generated {len(bundles)} mock bundles using real legal cases for query: {issue_text[:50]}...")
        
        return bundles
    
    async def _fallback_mock_response(
        self, 
        request: RetrievalRequest, 
        start_time: float
    ) -> RetrievalResponse:
        """Generate fallback mock response for demo purposes.
        
        Args:
            request: Original request
            start_time: Request start time
            
        Returns:
            Mock RetrievalResponse
        """
        logger.info("Generating fallback mock response for GraphRAG demo")
        
        mock_bundles = self._generate_mock_bundles(request.issue_text, request.limit)
        query_time_ms = int((time.time() - start_time) * 1000)
        
        return RetrievalResponse(
            bundles=mock_bundles,
            total_count=len(mock_bundles),
            query_time_ms=query_time_ms,
            graph_explanations=[],
            metrics=None
        )