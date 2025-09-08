"""
Bundle Generator Service - Uses GPT to generate relevant legal case bundles
"""

from typing import List, Dict, Any
import structlog
from openai import AsyncOpenAI
from datetime import datetime, timedelta
import random
import json

from ..core.config import settings
from ..models.schemas import ArgumentBundle, Case, Issue, ArgumentSegment

logger = structlog.get_logger()


class BundleGenerator:
    """Generate legal case bundles using GPT based on context"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.llm_model
    
    async def generate_bundles_from_context(
        self, 
        context: str, 
        num_bundles: int = 3
    ) -> List[ArgumentBundle]:
        """Generate relevant case bundles based on context using GPT
        
        Instead of searching databases, we use GPT to create relevant precedents
        that would logically support arguments for this type of case.
        
        Args:
            context: Case context description
            num_bundles: Number of bundles to generate
            
        Returns:
            List of ArgumentBundles with relevant precedents
        """
        
        # First, extract key information from context
        analysis_prompt = f"""Analyze this legal case and generate {num_bundles} relevant precedent cases that could be cited.

Context: {context}

For each precedent case, provide in JSON array format:
1. case_caption: Realistic case name (e.g., "Smith v. Jones Corp")
2. court: Court name (e.g., "U.S. District Court, Southern District of New York")
3. issue_type: Legal issue (e.g., "Trade Secret Misappropriation")
4. key_argument: Main legal argument from that case (100-150 words)
5. supporting_rule: Legal rule or statute that applies (50-100 words)
6. outcome: How the case was decided (e.g., "Plaintiff prevailed on trade secret claims")
7. relevance_score: 0.7 to 0.95 (how relevant to current case)

Generate {num_bundles} different precedents that would be most relevant.
Return ONLY the JSON array, no explanation."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a legal research assistant finding relevant precedents."},
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=0.7,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            # Parse GPT response
            content = response.choices[0].message.content
            
            # Try to extract JSON from response
            try:
                # Handle case where GPT returns object with "cases" key
                parsed = json.loads(content)
                if isinstance(parsed, dict) and "cases" in parsed:
                    precedents = parsed["cases"]
                elif isinstance(parsed, dict) and "precedents" in parsed:
                    precedents = parsed["precedents"]
                elif isinstance(parsed, list):
                    precedents = parsed
                else:
                    # If structure is unexpected, create from the dict
                    precedents = [parsed] if parsed else []
            except:
                logger.error(f"Failed to parse GPT response: {content}")
                precedents = []
            
            # Convert to ArgumentBundles
            bundles = []
            for i, precedent in enumerate(precedents[:num_bundles]):
                bundle = self._create_bundle_from_precedent(precedent, i)
                bundles.append(bundle)
            
            # If we don't have enough, generate generic ones
            while len(bundles) < num_bundles:
                bundles.append(self._create_generic_bundle(len(bundles)))
            
            return bundles[:num_bundles]
            
        except Exception as e:
            logger.error(f"Error generating bundles: {e}")
            # Fallback to generic bundles
            return [self._create_generic_bundle(i) for i in range(num_bundles)]
    
    def _create_bundle_from_precedent(self, precedent: Dict[str, Any], index: int) -> ArgumentBundle:
        """Convert GPT-generated precedent to ArgumentBundle
        
        Args:
            precedent: Dict with case information from GPT
            index: Bundle index
            
        Returns:
            ArgumentBundle
        """
        case_id = f"gpt_case_{index:03d}"
        
        # Extract fields with defaults
        case_caption = precedent.get("case_caption", f"Case {index+1} v. Defendant")
        court = precedent.get("court", "Superior Court")
        issue_type = precedent.get("issue_type", "Legal Dispute")
        key_argument = precedent.get("key_argument", "The court found in favor of the plaintiff based on established precedent.")
        supporting_rule = precedent.get("supporting_rule", "The applicable legal standard supports this position.")
        outcome = precedent.get("outcome", "Favorable ruling")
        relevance_score = float(precedent.get("relevance_score", 0.85))
        
        # Create bundle
        bundle = ArgumentBundle(
            argument_id=f"gpt_arg_{index:03d}",
            confidence={
                "value": relevance_score,
                "features": {
                    "vector_similarity": relevance_score,
                    "graph_relevance": relevance_score * 0.9,
                    "gpt_generated": True
                }
            },
            case=Case(
                id=case_id,
                caption=case_caption,
                court=court,
                jurisdiction="US",
                filed_date=datetime.now() - timedelta(days=random.randint(180, 1800))
            ),
            issue=Issue(
                id=f"gpt_issue_{index:03d}",
                title=issue_type,
                taxonomy_path=["Law", "Precedent", issue_type]
            ),
            segments=[
                ArgumentSegment(
                    segment_id=f"gpt_seg_{case_id}_00",
                    argument_id=f"gpt_arg_{index:03d}",
                    text=key_argument,
                    role="opening",  # Valid enum value
                    seq=0,
                    citations=self._extract_citations(supporting_rule)
                ),
                ArgumentSegment(
                    segment_id=f"gpt_seg_{case_id}_01",
                    argument_id=f"gpt_arg_{index:03d}",
                    text=supporting_rule,
                    role="rebuttal",  # Valid enum value
                    seq=1,
                    citations=[]
                ),
                ArgumentSegment(
                    segment_id=f"gpt_seg_{case_id}_02",
                    argument_id=f"gpt_arg_{index:03d}",
                    text=f"Outcome: {outcome}",
                    role="closing",  # Valid enum value
                    seq=2,
                    citations=[]
                )
            ],
            metadata={
                "gpt_generated": True,
                "outcome": outcome,
                "relevance_explanation": f"Relevant to current case based on {issue_type}"
            }
        )
        
        return bundle
    
    def _create_generic_bundle(self, index: int) -> ArgumentBundle:
        """Create a generic bundle as fallback
        
        Args:
            index: Bundle index
            
        Returns:
            Generic ArgumentBundle
        """
        case_id = f"generic_case_{index:03d}"
        
        return ArgumentBundle(
            argument_id=f"generic_arg_{index:03d}",
            confidence={
                "value": 0.75,
                "features": {
                    "vector_similarity": 0.75,
                    "graph_relevance": 0.70,
                    "gpt_generated": True
                }
            },
            case=Case(
                id=case_id,
                caption=f"Precedent Case {index+1} v. Respondent",
                court="District Court",
                jurisdiction="US",
                filed_date=datetime.now() - timedelta(days=random.randint(30, 365))
            ),
            issue=Issue(
                id=f"generic_issue_{index:03d}",
                title="Legal Precedent",
                taxonomy_path=["Law", "General", "Precedent"]
            ),
            segments=[
                ArgumentSegment(
                    segment_id=f"generic_seg_{case_id}_00",
                    argument_id=f"generic_arg_{index:03d}",
                    text="Based on established legal principles and prior court decisions, the argument is supported by precedent.",
                    role="opening",  # Valid enum value
                    seq=0,
                    citations=["Legal Code § 100"]
                )
            ],
            metadata={
                "gpt_generated": True,
                "generic": True
            }
        )
    
    def _extract_citations(self, text: str) -> List[str]:
        """Extract citations from text
        
        Simple extraction of patterns like "§ 123" or "U.S.C."
        
        Args:
            text: Text to extract from
            
        Returns:
            List of citations
        """
        import re
        
        citations = []
        
        # Find section references
        section_pattern = r'§\s*\d+'
        citations.extend(re.findall(section_pattern, text))
        
        # Find U.S.C. references
        usc_pattern = r'\d+\s+U\.S\.C\.\s*§?\s*\d+'
        citations.extend(re.findall(usc_pattern, text))
        
        # Find case citations (simplified)
        case_pattern = r'[A-Z][a-z]+\s+v\.\s+[A-Z][a-z]+'
        citations.extend(re.findall(case_pattern, text))
        
        return citations[:5]  # Limit to 5 citations