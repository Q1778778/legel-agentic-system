"""
Context Parser Service - Uses GPT to intelligently parse case context
"""

from typing import Dict, Any, Optional
import structlog
from openai import AsyncOpenAI
from ..core.config import settings

logger = structlog.get_logger()


class ContextParser:
    """Parse legal context using GPT to extract key information"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.llm_model
    
    async def parse_context(self, context: str) -> Dict[str, Any]:
        """Parse case context to extract structured information
        
        Args:
            context: Raw case context from user
            
        Returns:
            Structured information including:
            - issue_type: Main legal issue (for searching similar cases)
            - parties: Plaintiff and defendant
            - claims: Key claims being made
            - jurisdiction: Inferred jurisdiction
            - key_facts: Important facts
        """
        
        prompt = f"""Analyze this legal case context and extract key information.
        
        Context: {context}
        
        Extract and return in JSON format:
        1. issue_type: The main legal issue in 2-4 words (e.g., "patent infringement", "contract breach", "personal injury")
        2. plaintiff: Name of plaintiff/complainant
        3. defendant: Name of defendant/respondent  
        4. claims: List of main claims (max 3)
        5. jurisdiction: Likely jurisdiction (US, UK, EU, etc.)
        6. key_facts: List of 3-5 most important facts
        7. search_query: Optimal search query for finding similar cases (10-15 words)
        
        Return ONLY valid JSON, no explanation."""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a legal analyst expert at parsing case information."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent parsing
                max_tokens=500,
                response_format={"type": "json_object"}  # Force JSON response
            )
            
            import json
            parsed = json.loads(response.choices[0].message.content)
            
            # Ensure all expected fields exist
            return {
                "issue_type": parsed.get("issue_type", "general legal dispute"),
                "plaintiff": parsed.get("plaintiff", "Unknown"),
                "defendant": parsed.get("defendant", "Unknown"),
                "claims": parsed.get("claims", []),
                "jurisdiction": parsed.get("jurisdiction", "US"),
                "key_facts": parsed.get("key_facts", []),
                "search_query": parsed.get("search_query", context[:100])
            }
            
        except Exception as e:
            logger.error(f"Error parsing context: {e}")
            # Fallback to simple extraction
            return {
                "issue_type": "legal dispute",
                "plaintiff": "Party A",
                "defendant": "Party B",
                "claims": ["Dispute over agreement"],
                "jurisdiction": "US",
                "key_facts": [context[:200]],
                "search_query": context[:100]
            }
    
    async def generate_search_query(self, context: str) -> str:
        """Generate optimal search query from context
        
        Args:
            context: Case context
            
        Returns:
            Optimized search query for GraphRAG retrieval
        """
        
        prompt = f"""Based on this legal case context, generate the BEST search query 
        to find similar past cases. The query should focus on the core legal issue.
        
        Context: {context}
        
        Return ONLY the search query (10-20 words), nothing else."""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a legal search expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=50
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Error generating search query: {e}")
            # Fallback: use first 100 chars
            return context[:100]