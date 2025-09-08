"""Multi-agent analysis service for legal arguments."""

from typing import List, Dict, Any, Optional
import time
import structlog
from openai import AsyncOpenAI

from ..core.config import settings
from ..models.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisArtifact,
    ArgumentBundle,
)

logger = structlog.get_logger()


class LegalAnalysisService:
    """Service for analyzing legal arguments using multi-agent approach."""
    
    def __init__(self):
        """Initialize legal analysis service."""
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
    
    async def analyze(
        self,
        request: AnalysisRequest,
    ) -> AnalysisResponse:
        """Analyze legal arguments based on retrieved bundles.
        
        Args:
            request: Analysis request with bundles and context
            
        Returns:
            Analyzed arguments from defense, prosecution, and judge
        """
        start_time = time.time()
        
        try:
            # Build context from bundles
            context = self._build_context(request.bundles, request.context)
            
            # Generate defense argument
            defense = await self._generate_defense(context, request.bundles)
            
            # Generate prosecution counter if requested
            prosecution = None
            if request.include_prosecution:
                prosecution = await self._generate_prosecution(context, defense)
            
            # Generate judge questions if requested
            judge = None
            if request.include_judge:
                judge = await self._generate_judge_questions(context, defense, prosecution)
            
            # Generate oral argument script
            script = None
            if defense and (prosecution or judge):
                script = await self._generate_script(defense, prosecution, judge)
            
            # Calculate overall confidence
            confidences = [defense.confidence]
            if prosecution:
                confidences.append(prosecution.confidence)
            if judge:
                confidences.append(judge.confidence)
            overall_confidence = sum(confidences) / len(confidences)
            
            generation_time_ms = int((time.time() - start_time) * 1000)
            
            return AnalysisResponse(
                defense=defense,
                prosecution=prosecution,
                judge=judge,
                script=script,
                overall_confidence=overall_confidence,
                generation_time_ms=generation_time_ms,
            )
            
        except Exception as e:
            logger.error(f"Error in analysis: {e}")
            raise
    
    def _build_context(
        self,
        bundles: List[ArgumentBundle],
        additional_context: Optional[str] = None,
    ) -> str:
        """Build context from argument bundles.
        
        Args:
            bundles: List of argument bundles
            additional_context: Additional context from user
            
        Returns:
            Context string for simulation
        """
        context_parts = []
        
        # Add case information
        if bundles:
            first_bundle = bundles[0]
            context_parts.append(f"Case: {first_bundle.case.caption or 'Unknown'}")
            context_parts.append(f"Issue: {first_bundle.issue.title}")
            context_parts.append(f"Jurisdiction: {first_bundle.case.jurisdiction or 'Unknown'}")
            
            if first_bundle.case.judge_name:
                context_parts.append(f"Judge: {first_bundle.case.judge_name}")
        
        # Add key arguments and citations
        context_parts.append("\nKey Past Arguments:")
        for bundle in bundles[:3]:  # Top 3 bundles
            for segment in bundle.segments[:2]:  # Top 2 segments per bundle
                context_parts.append(f"- {segment.text[:200]}...")
                if segment.citations:
                    context_parts.append(f"  Citations: {', '.join(segment.citations[:3])}")
        
        # Add additional context
        if additional_context:
            context_parts.append(f"\nAdditional Context:\n{additional_context}")
        
        return "\n".join(context_parts)
    
    async def _generate_defense(
        self,
        context: str,
        bundles: List[ArgumentBundle],
    ) -> AnalysisArtifact:
        """Generate defense argument.
        
        Args:
            context: Context for generation
            bundles: Argument bundles for reference
            
        Returns:
            Defense argument artifact
        """
        # Extract citations from bundles
        all_citations = set()
        for bundle in bundles:
            for segment in bundle.segments:
                all_citations.update(segment.citations)
        
        citations_list = list(all_citations)[:10]  # Limit to 10 citations
        
        prompt = f"""You are a defense attorney. Based on the following case context and past successful cases,
        generate a compelling defense argument using the IRAC structure (Issue, Rule, Application, Conclusion).
        
        Case Context:
        {context}
        
        Available Citations:
        {', '.join(citations_list)}
        
        Requirements:
        1. Use only the citations provided above
        2. Organize arguments using IRAC format
        3. Be concise yet comprehensive (max 500 words)
        4. Focus on the most compelling precedents
        5. Use professional legal language
        
        Generate the defense argument:"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an experienced defense attorney."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=1000,
            )
            
            text = response.choices[0].message.content
            
            # Calculate confidence based on bundle scores
            confidence = sum(b.confidence.value for b in bundles[:3]) / min(3, len(bundles))
            
            return AnalysisArtifact(
                text=text,
                confidence=confidence,
                role="defense",
                citations_used=citations_list[:5],
            )
            
        except Exception as e:
            logger.error(f"Error generating defense: {e}")
            raise
    
    async def _generate_prosecution(
        self,
        context: str,
        defense: AnalysisArtifact,
    ) -> AnalysisArtifact:
        """Generate prosecution counter-argument.
        
        Args:
            context: Context for generation
            defense: Defense argument to counter
            
        Returns:
            Prosecution argument artifact
        """
        prompt = f"""You are a prosecutor. Review the following defense argument and generate a compelling counter-argument.
        
        Case Context:
        {context}
        
        Defense Argument:
        {defense.text}
        
        Requirements:
        1. Identify weaknesses in the defense argument
        2. Distinguish cited cases where possible
        3. Present alternative interpretations
        4. Be concise yet comprehensive (max 400 words)
        5. Use professional prosecutorial language
        
        Generate the prosecution's counter-argument:"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an experienced prosecutor."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=800,
            )
            
            text = response.choices[0].message.content
            
            return AnalysisArtifact(
                text=text,
                confidence=defense.confidence * 0.9,  # Slightly lower confidence
                role="prosecution",
                citations_used=[],
            )
            
        except Exception as e:
            logger.error(f"Error generating prosecution: {e}")
            raise
    
    async def _generate_judge_questions(
        self,
        context: str,
        defense: AnalysisArtifact,
        prosecution: Optional[AnalysisArtifact] = None,
    ) -> AnalysisArtifact:
        """Generate judge's bench questions.
        
        Args:
            context: Context for generation
            defense: Defense argument
            prosecution: Optional prosecution argument
            
        Returns:
            Judge questions artifact
        """
        prompt = f"""You are the presiding judge. Review both parties' arguments and generate insightful bench questions.
        
        Case Context:
        {context}
        
        Defense Argument:
        {defense.text}
        """
        
        if prosecution:
            prompt += f"\n\nProsecution Argument:\n{prosecution.text}"
        
        prompt += """
        
        Requirements:
        1. Ask clarifying questions about legal reasoning
        2. Probe potential weaknesses
        3. Test understanding of precedents
        4. Generate 3-5 specific questions
        5. Use formal judicial language
        
        Generate bench questions:"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an experienced judge."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature * 0.8,  # Slightly lower temperature for judge
                max_tokens=500,
            )
            
            text = response.choices[0].message.content
            
            return AnalysisArtifact(
                text=text,
                confidence=defense.confidence,
                role="judge",
                citations_used=[],
            )
            
        except Exception as e:
            logger.error(f"Error generating judge questions: {e}")
            raise
    
    async def _generate_script(
        self,
        defense: AnalysisArtifact,
        prosecution: Optional[AnalysisArtifact],
        judge: Optional[AnalysisArtifact],
    ) -> AnalysisArtifact:
        """Generate oral argument script.
        
        Args:
            defense: Defense argument
            prosecution: Optional prosecution argument
            judge: Optional judge questions
            
        Returns:
            Oral argument script artifact
        """
        prompt = """Compress the following arguments into a concise oral argument script.
        
        Defense:
        {defense.text[:500]}...
        """
        
        if prosecution:
            prompt += f"\n\nProsecution:\n{prosecution.text[:300]}..."
        
        if judge:
            prompt += f"\n\nJudge Questions:\n{judge.text[:300]}..."
        
        prompt += """
        
        Create a structured oral argument script with:
        1. Opening statement (1 minute)
        2. Main arguments (2-3 minutes)
        3. Responses to anticipated questions
        4. Closing (30 seconds)
        
        Generate the script:"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a legal script writer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature * 0.9,
                max_tokens=800,
            )
            
            text = response.choices[0].message.content
            
            return AnalysisArtifact(
                text=text,
                confidence=defense.confidence,
                role="script",
                citations_used=defense.citations_used,
            )
            
        except Exception as e:
            logger.error(f"Error generating script: {e}")
            raise