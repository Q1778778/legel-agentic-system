"""Microsoft GraphRAG integration service for legal document retrieval."""

import os
import asyncio
from typing import List, Dict, Any, Optional
import structlog
import time
from pathlib import Path

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
            cmd = ["graphrag", "query", "--method", "local", "--query", query]
            
            result = subprocess.run(
                cmd,
                cwd=self.graphrag_data_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                # Parse the output to extract the response text
                output_lines = result.stdout.split('\n')
                # Find the response after the log lines
                response_started = False
                response_lines = []
                
                for line in output_lines:
                    if 'Local Search Response:' in line:
                        response_started = True
                        continue
                    if response_started and line.strip():
                        response_lines.append(line)
                
                return '\n'.join(response_lines).strip()
            else:
                logger.error(f"GraphRAG local search failed: {result.stderr}")
                return ""
                
        except Exception as e:
            logger.error(f"Local search error: {e}")
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
            cmd = ["graphrag", "query", "--method", "global", "--query", query]
            
            result = subprocess.run(
                cmd,
                cwd=self.graphrag_data_dir,
                capture_output=True,
                text=True,
                timeout=90  # Global search takes longer
            )
            
            if result.returncode == 0:
                # Parse the output to extract the response text
                output_lines = result.stdout.split('\n')
                # Find the response after the log lines
                response_started = False
                response_lines = []
                
                for line in output_lines:
                    if 'Global Search Response:' in line:
                        response_started = True
                        continue
                    if response_started and line.strip():
                        response_lines.append(line)
                
                return '\n'.join(response_lines).strip()
            else:
                logger.error(f"GraphRAG global search failed: {result.stderr}")
                return ""
                
        except Exception as e:
            logger.error(f"Global search error: {e}")
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
        import hashlib
        import random
        from datetime import datetime, timedelta
        
        # Generate consistent ID based on content
        content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        bundle_id = f"graphrag_{source_type}_{content_hash}"
        
        # Extract key information from the text (simplified)
        # In production, you'd use more sophisticated parsing
        lines = text.split('\n')
        key_points = [line.strip() for line in lines if line.strip() and not line.startswith('#')]
        
        # Create segments from the key points
        segments = []
        for i, point in enumerate(key_points[:5]):  # Limit to 5 segments
            if len(point) > 20:  # Only include substantial points
                segment = ArgumentSegment(
                    segment_id=f"{bundle_id}_seg_{i:02d}",
                    argument_id=bundle_id,
                    text=point,
                    role="analysis",
                    seq=i,
                    citations=[]
                )
                segments.append(segment)
        
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
            segments=segments,
            metadata={
                "source": "microsoft_graphrag",
                "search_type": source_type,
                "query": request.issue_text,
                "response_length": len(text)
            }
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
            source_type = bundle.metadata.get("search_type", "unknown")
            
            explanation = GraphExplanation(
                argument_id=bundle.argument_id,
                paths=[{
                    "type": f"graphrag_{source_type}",
                    "nodes": ["Query", "GraphRAG_Index", "Legal_Entities", "Analysis"],
                    "confidence": bundle.confidence.value
                }],
                key_nodes=["Legal_Cases", "Entities", "Relationships", "Communities"],
                explanation_text=f"Found via Microsoft GraphRAG {source_type} search using knowledge graph analysis of legal documents"
            )
            explanations.append(explanation)
        
        return explanations
    
    def _generate_mock_bundles(self, issue_text: str, limit: int) -> List[ArgumentBundle]:
        """Generate mock argument bundles when no results are found.
        
        Args:
            issue_text: Query text
            limit: Number of bundles to generate
            
        Returns:
            List of mock ArgumentBundles
        """
        bundles = []
        
        # Enhanced mock data based on common legal issues
        mock_cases = [
            {
                "caption": "GraphRAG Legal Analysis - Patent Dispute",
                "court": "U.S. District Court, Technology Division",
                "issue_title": "Patent Infringement Analysis",
                "segments": [
                    "The defendant's product implements similar technical features to the patented invention, requiring detailed claim-by-claim analysis.",
                    "Prior art search reveals potential invalidity defenses that could limit patent scope and enforceability.",
                    "Damages calculation must consider reasonable royalty rates and defendant's actual profits from infringing sales."
                ]
            },
            {
                "caption": "GraphRAG Legal Analysis - Contract Breach",
                "court": "State Superior Court, Commercial Division", 
                "issue_title": "Contract Performance and Breach",
                "segments": [
                    "Material breach analysis requires examining whether party's non-performance substantially frustrated the contract's purpose.",
                    "Force majeure clauses may excuse performance if unforeseeable circumstances prevented contract fulfillment.",
                    "Mitigation of damages doctrine requires injured party to take reasonable steps to minimize losses."
                ]
            }
        ]
        
        for i, template in enumerate(mock_cases[:limit]):
            bundle_id = f"mock_graphrag_{i:03d}"
            
            segments = [
                ArgumentSegment(
                    segment_id=f"{bundle_id}_seg_{j:02d}",
                    argument_id=bundle_id,
                    text=text,
                    role="analysis",
                    seq=j,
                    citations=[]
                )
                for j, text in enumerate(template["segments"])
            ]
            
            case = Case(
                id=f"mock_case_{i:03d}",
                caption=template["caption"],
                court=template["court"], 
                jurisdiction="US",
                filed_date=datetime.now() - timedelta(days=30)
            )
            
            issue = Issue(
                id=f"mock_issue_{i:03d}",
                title=template["issue_title"],
                taxonomy_path=["Law", "GraphRAG", template["issue_title"]]
            )
            
            confidence = ConfidenceScore(
                value=0.75,
                features={
                    "graphrag_mock": True,
                    "relevance": 0.75
                }
            )
            
            bundle = ArgumentBundle(
                argument_id=bundle_id,
                confidence=confidence,
                case=case,
                issue=issue,
                segments=segments,
                metadata={
                    "source": "microsoft_graphrag_mock",
                    "is_demo": True
                }
            )
            
            bundles.append(bundle)
        
        return bundles[:limit]
    
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