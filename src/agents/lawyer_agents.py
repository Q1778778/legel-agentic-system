"""Specialized lawyer agents for legal argumentation."""

from typing import List, Dict, Any, Optional
from .base_agent import BaseAgent, AgentMessage, AgentContext
import structlog

logger = structlog.get_logger()


class LawyerAgent(BaseAgent):
    """Base lawyer agent for single-lawyer mode analysis."""
    
    def get_system_prompt(self) -> str:
        """Get system prompt for lawyer agent."""
        return """You are an experienced legal professional analyzing legal arguments.
        
Your role is to:
1. Analyze the legal issue and relevant precedents
2. Identify strengths and weaknesses in arguments
3. Suggest improvements and alternative approaches
4. Cite relevant cases and statutes
5. Provide strategic recommendations

Always maintain professional legal language and cite specific precedents when possible."""
    
    async def process(self, context: AgentContext) -> AgentMessage:
        """Process context and generate legal analysis.
        
        Args:
            context: Current case context
            
        Returns:
            Analysis message
        """
        # Build messages for LLM
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": self._build_analysis_prompt(context)}
        ]
        
        # Add any previous messages for context
        for msg in context.messages[-3:]:  # Last 3 messages for context
            messages.append({
                "role": "assistant" if msg.role != "user" else "user",
                "content": msg.content
            })
        
        # Generate response
        content = await self._call_llm(messages, tools=self.tools)
        
        # Extract citations and calculate confidence
        citations = self._extract_citations(content)
        confidence = self._calculate_confidence(content, citations)
        
        return AgentMessage(
            role=self.role,
            content=content,
            citations=citations,
            confidence=confidence,
            metadata={
                "agent": self.name,
                "turn": context.current_turn,
                "bundles_used": len(context.bundles)
            }
        )
    
    def _build_analysis_prompt(self, context: AgentContext) -> str:
        """Build the analysis prompt from context.
        
        Args:
            context: Current case context
            
        Returns:
            Formatted prompt
        """
        prompt = f"""Analyze the following legal issue:

Issue: {context.issue_text}

Case ID: {context.case_id}

"""
        
        if context.bundles:
            prompt += "Relevant Past Cases and Arguments:\n"
            for i, bundle in enumerate(context.bundles[:3], 1):
                case = bundle.get("case", {})
                prompt += f"\n{i}. {case.get('caption', 'Unknown Case')}"
                prompt += f"\n   Court: {case.get('court', 'Unknown Court')}"
                
                segments = bundle.get("segments", [])
                if segments:
                    prompt += f"\n   Key Argument: {segments[0].get('text', '')[:200]}..."
        
        prompt += "\n\nProvide a comprehensive legal analysis with specific recommendations."
        
        return prompt


class ProsecutorAgent(BaseAgent):
    """Prosecutor agent for debate mode."""
    
    def get_system_prompt(self) -> str:
        """Get system prompt for prosecutor agent."""
        return """You are an experienced prosecutor presenting arguments in court.

Your role is to:
1. Present strong arguments for the prosecution
2. Challenge the defense's claims with evidence and precedent
3. Cite relevant cases that support prosecution
4. Maintain aggressive but professional demeanor
5. Focus on establishing guilt/liability beyond reasonable doubt

Style: Assertive, fact-based, methodical. Use phrases like "The evidence clearly shows...", 
"The defendant's actions demonstrate...", "Precedent in [case] establishes..."."""
    
    async def process(self, context: AgentContext) -> AgentMessage:
        """Generate prosecution argument.
        
        Args:
            context: Current debate context
            
        Returns:
            Prosecution message
        """
        # Check if we're responding to defense
        last_defense = None
        defense_messages = context.get_messages_by_role("defender")
        if defense_messages:
            last_defense = defense_messages[-1]
        
        # Build messages
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": self._build_prosecution_prompt(context, last_defense)}
        ]
        
        # Generate response
        content = await self._call_llm(messages, tools=self.tools)
        
        # Extract citations and calculate confidence
        citations = self._extract_citations(content)
        confidence = self._calculate_prosecution_confidence(content, citations, context)
        
        return AgentMessage(
            role="prosecutor",
            content=content,
            citations=citations,
            confidence=confidence,
            metadata={
                "agent": self.name,
                "turn": context.current_turn,
                "responding_to": last_defense.metadata.get("agent") if last_defense else None
            }
        )
    
    def _build_prosecution_prompt(
        self, 
        context: AgentContext, 
        last_defense: Optional[AgentMessage]
    ) -> str:
        """Build prosecution prompt.
        
        Args:
            context: Current debate context
            last_defense: Last defense message if any
            
        Returns:
            Formatted prompt
        """
        prompt = f"""Legal Issue: {context.issue_text}

Case: {context.case_id}

"""
        
        if last_defense:
            prompt += f"""The defense argues:
"{last_defense.content[:500]}..."

Provide a strong prosecutorial response that:
1. Directly rebuts the defense's claims
2. Presents counter-evidence and precedents
3. Strengthens the prosecution's position
"""
        else:
            prompt += """Present the prosecution's opening argument that:
1. Clearly states the charges/claims
2. Outlines the key evidence
3. Cites relevant precedents
4. Establishes the legal framework
"""
        
        if context.bundles:
            prompt += "\n\nRelevant precedents from database:\n"
            for bundle in context.bundles[:2]:
                case = bundle.get("case", {})
                if bundle.get("metadata", {}).get("outcome") == "granted":
                    prompt += f"- {case.get('caption')}: Prosecution prevailed\n"
        
        return prompt
    
    def _calculate_prosecution_confidence(
        self, 
        content: str, 
        citations: List[str],
        context: AgentContext
    ) -> float:
        """Calculate prosecution-specific confidence.
        
        Args:
            content: Response content
            citations: Citations used
            context: Current context
            
        Returns:
            Confidence score
        """
        base_confidence = self._calculate_confidence(content, citations)
        
        # Boost for aggressive language
        aggressive_terms = ["clearly", "undeniably", "demonstrates", "proves", "established"]
        term_boost = sum(0.02 for term in aggressive_terms if term in content.lower())
        
        # Boost if responding to defense
        if context.get_messages_by_role("defender"):
            base_confidence += 0.1
        
        return min(base_confidence + term_boost, 0.95)


class DefenderAgent(BaseAgent):
    """Defense attorney agent for debate mode."""
    
    def get_system_prompt(self) -> str:
        """Get system prompt for defender agent."""
        return """You are an experienced defense attorney protecting your client's interests.

Your role is to:
1. Present strong defensive arguments
2. Challenge prosecution claims and evidence
3. Cite precedents that favor the defense
4. Protect constitutional rights and due process
5. Create reasonable doubt about prosecution's case

Style: Protective, strategic, emphatic. Use phrases like "The prosecution fails to prove...", 
"My client's rights were violated when...", "The precedent in [case] protects..."."""
    
    async def process(self, context: AgentContext) -> AgentMessage:
        """Generate defense argument.
        
        Args:
            context: Current debate context
            
        Returns:
            Defense message
        """
        # Check if we're responding to prosecution
        last_prosecution = None
        prosecution_messages = context.get_messages_by_role("prosecutor")
        if prosecution_messages:
            last_prosecution = prosecution_messages[-1]
        
        # Build messages
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": self._build_defense_prompt(context, last_prosecution)}
        ]
        
        # Generate response
        content = await self._call_llm(messages, tools=self.tools)
        
        # Extract citations and calculate confidence
        citations = self._extract_citations(content)
        confidence = self._calculate_defense_confidence(content, citations, context)
        
        return AgentMessage(
            role="defender",
            content=content,
            citations=citations,
            confidence=confidence,
            metadata={
                "agent": self.name,
                "turn": context.current_turn,
                "responding_to": last_prosecution.metadata.get("agent") if last_prosecution else None
            }
        )
    
    def _build_defense_prompt(
        self,
        context: AgentContext,
        last_prosecution: Optional[AgentMessage]
    ) -> str:
        """Build defense prompt.
        
        Args:
            context: Current debate context
            last_prosecution: Last prosecution message if any
            
        Returns:
            Formatted prompt
        """
        prompt = f"""Legal Issue: {context.issue_text}

Case: {context.case_id}

"""
        
        if last_prosecution:
            prompt += f"""The prosecution argues:
"{last_prosecution.content[:500]}..."

Provide a strong defensive response that:
1. Challenges the prosecution's assertions
2. Presents exculpatory evidence or interpretations
3. Cites cases that support the defense
4. Protects the client's rights
"""
        else:
            prompt += """Present the defense's opening argument that:
1. Challenges the prosecution's ability to prove their case
2. Presents alternative interpretations of facts
3. Cites protective precedents
4. Emphasizes reasonable doubt or lack of liability
"""
        
        if context.bundles:
            prompt += "\n\nRelevant precedents from database:\n"
            for bundle in context.bundles[:2]:
                case = bundle.get("case", {})
                if bundle.get("metadata", {}).get("outcome") == "denied":
                    prompt += f"- {case.get('caption')}: Defense prevailed\n"
        
        return prompt
    
    def _calculate_defense_confidence(
        self,
        content: str,
        citations: List[str],
        context: AgentContext
    ) -> float:
        """Calculate defense-specific confidence.
        
        Args:
            content: Response content
            citations: Citations used
            context: Current context
            
        Returns:
            Confidence score
        """
        base_confidence = self._calculate_confidence(content, citations)
        
        # Boost for protective language
        protective_terms = ["rights", "reasonable doubt", "fails to prove", "constitutional", "protected"]
        term_boost = sum(0.02 for term in protective_terms if term in content.lower())
        
        # Boost if successfully challenging prosecution
        if context.get_messages_by_role("prosecutor"):
            base_confidence += 0.1
        
        return min(base_confidence + term_boost, 0.95)


class FeedbackAgent(BaseAgent):
    """Feedback agent that analyzes and improves arguments."""
    
    def get_system_prompt(self) -> str:
        """Get system prompt for feedback agent."""
        return """You are a senior legal analyst and former judge providing expert feedback on legal arguments.

Your role is to:
1. Analyze the strengths and weaknesses of both sides
2. Identify missing arguments or precedents
3. Suggest improvements for each side
4. Evaluate the likely outcome based on arguments presented
5. Provide balanced, constructive criticism

Style: Analytical, balanced, constructive. Use phrases like "The prosecution could strengthen...", 
"The defense missed an opportunity to...", "Based on precedent, the court would likely..."."""
    
    async def process(self, context: AgentContext) -> AgentMessage:
        """Generate feedback on the debate.
        
        Args:
            context: Current debate context
            
        Returns:
            Feedback message
        """
        # Analyze all messages
        prosecution_msgs = context.get_messages_by_role("prosecutor")
        defense_msgs = context.get_messages_by_role("defender")
        
        # Build messages
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": self._build_feedback_prompt(
                context, prosecution_msgs, defense_msgs
            )}
        ]
        
        # Generate response
        content = await self._call_llm(messages, tools=self.tools)
        
        # Calculate overall debate quality
        confidence = self._calculate_debate_quality(prosecution_msgs, defense_msgs)
        
        return AgentMessage(
            role="feedback",
            content=content,
            citations=self._extract_citations(content),
            confidence=confidence,
            metadata={
                "agent": self.name,
                "turn": context.current_turn,
                "prosecution_turns": len(prosecution_msgs),
                "defense_turns": len(defense_msgs),
                "debate_quality": confidence
            }
        )
    
    def _build_feedback_prompt(
        self,
        context: AgentContext,
        prosecution_msgs: List[AgentMessage],
        defense_msgs: List[AgentMessage]
    ) -> str:
        """Build feedback prompt.
        
        Args:
            context: Current debate context
            prosecution_msgs: All prosecution messages
            defense_msgs: All defense messages
            
        Returns:
            Formatted prompt
        """
        prompt = f"""Analyze this legal debate:

Issue: {context.issue_text}
Case: {context.case_id}

PROSECUTION ARGUMENTS:
"""
        for i, msg in enumerate(prosecution_msgs, 1):
            prompt += f"\n{i}. {msg.content[:300]}..."
            if msg.citations:
                prompt += f"\n   Citations: {', '.join(msg.citations[:3])}"
        
        prompt += "\n\nDEFENSE ARGUMENTS:\n"
        for i, msg in enumerate(defense_msgs, 1):
            prompt += f"\n{i}. {msg.content[:300]}..."
            if msg.citations:
                prompt += f"\n   Citations: {', '.join(msg.citations[:3])}"
        
        prompt += """

Provide comprehensive feedback that:
1. Evaluates the strength of each side's arguments
2. Identifies missed opportunities or weak points
3. Suggests specific improvements with case citations
4. Predicts the likely outcome based on arguments presented
5. Rates the overall quality of the legal debate

Format your response with clear sections for Prosecution Analysis, Defense Analysis, 
Missing Arguments, and Predicted Outcome."""
        
        return prompt
    
    def _calculate_debate_quality(
        self,
        prosecution_msgs: List[AgentMessage],
        defense_msgs: List[AgentMessage]
    ) -> float:
        """Calculate overall debate quality.
        
        Args:
            prosecution_msgs: Prosecution messages
            defense_msgs: Defense messages
            
        Returns:
            Quality score between 0 and 1
        """
        if not prosecution_msgs and not defense_msgs:
            return 0.0
        
        # Calculate average confidence of all messages
        all_confidences = (
            [msg.confidence for msg in prosecution_msgs] +
            [msg.confidence for msg in defense_msgs]
        )
        
        if not all_confidences:
            return 0.5
        
        avg_confidence = sum(all_confidences) / len(all_confidences)
        
        # Boost for balanced debate
        balance_boost = 0.0
        if prosecution_msgs and defense_msgs:
            ratio = len(prosecution_msgs) / len(defense_msgs)
            if 0.5 <= ratio <= 2.0:  # Relatively balanced
                balance_boost = 0.1
        
        # Boost for citations
        total_citations = sum(
            len(msg.citations) for msg in prosecution_msgs + defense_msgs
        )
        citation_boost = min(total_citations * 0.02, 0.2)
        
        return min(avg_confidence + balance_boost + citation_boost, 0.95)