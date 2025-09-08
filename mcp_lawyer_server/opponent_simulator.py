"""Opponent simulation module for anticipating opposing counsel's arguments."""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
import json
import os
from agents import Agent, run

from legal_context import ArgumentContext, LawyerInfo
from graphrag_retrieval import GraphRAGRetrieval

logger = structlog.get_logger()


class OpponentSimulator:
    """Simulates opposing counsel's responses and arguments."""
    
    def __init__(
        self,
        graphrag_base_url: str,
        openai_client: Any,
        config: Dict[str, Any]
    ):
        """Initialize opponent simulator.
        
        Args:
            graphrag_base_url: Base URL for GraphRAG API
            openai_client: OpenAI client instance
            config: Configuration dictionary
        """
        self.graphrag_base_url = graphrag_base_url
        self.openai_client = openai_client
        self.config = config
        self.search_strategy = config.get("search_strategy", {})
        self.max_precedents = config.get("max_precedents", 5)
        self.confidence_threshold = config.get("confidence_threshold", 0.65)
        
        # Initialize GraphRAGRetrieval
        self.graphrag_retrieval = GraphRAGRetrieval()
        
        # Initialize OpenAI Agent for legal reasoning
        self.legal_agent = Agent(
            name="Legal Analyst",
            model="gpt-4-turbo-preview",
            instructions="You are an expert legal analyst and opposing counsel simulator. Your task is to identify weaknesses in legal arguments and generate strong counter-arguments based on precedents."
        )
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def simulate_opponent_response(
        self,
        our_argument: str,
        case_context: Dict[str, Any],
        opposing_counsel: Optional[LawyerInfo] = None,
        our_position: Optional[str] = None
    ) -> Dict[str, Any]:
        """Simulate opposing counsel's response to our argument.
        
        Args:
            our_argument: Our legal argument
            case_context: Context about the case
            opposing_counsel: Information about opposing counsel
            our_position: Our position (plaintiff/defendant)
            
        Returns:
            Dictionary containing simulated response and analysis
        """
        try:
            # 1. Search for opposing precedents
            opposing_precedents = await self._search_opposing_precedents(
                our_argument,
                case_context,
                opposing_counsel
            )
            
            # 2. Identify weaknesses in our argument
            weaknesses = await self._identify_argument_weaknesses(
                our_argument,
                opposing_precedents
            )
            
            # 3. Generate opposing counsel's response
            response = await self._generate_opposing_response(
                our_argument,
                opposing_precedents,
                weaknesses,
                case_context,
                opposing_counsel
            )
            
            # 4. Assess response strength
            strength_assessment = self._assess_response_strength(
                response,
                opposing_precedents,
                weaknesses
            )
            
            # 5. Suggest counter-arguments
            counter_arguments = await self._generate_counter_arguments(
                response["argument"],
                our_argument,
                case_context
            )
            
            return {
                "opposing_argument": response["argument"],
                "supporting_precedents": opposing_precedents,
                "identified_weaknesses": weaknesses,
                "citations": response["citations"],
                "strength_assessment": strength_assessment,
                "suggested_counters": counter_arguments,
                "confidence": response["confidence"],
                "metadata": {
                    "opposing_counsel": opposing_counsel.to_dict() if opposing_counsel else None,
                    "simulation_timestamp": datetime.now().isoformat(),
                    "strategy_weights": self.search_strategy
                }
            }
            
        except Exception as e:
            logger.error(f"Error simulating opponent response: {e}")
            raise
            
    async def _search_opposing_precedents(
        self,
        our_argument: str,
        case_context: Dict[str, Any],
        opposing_counsel: Optional[LawyerInfo] = None
    ) -> List[Dict[str, Any]]:
        """Search for precedents that support the opposing position using GraphRAGRetrieval.
        
        Args:
            our_argument: Our legal argument
            case_context: Case context
            opposing_counsel: Opposing counsel info
            
        Returns:
            List of opposing precedents
        """
        try:
            # Construct search query for opposite outcomes
            search_query = self._construct_opposing_search_query(
                our_argument,
                case_context
            )
            
            # Use GraphRAGRetrieval directly
            precedents = await self.graphrag_retrieval.retrieve_past_defenses(
                issue_text=search_query,
                lawyer_id=opposing_counsel.id if opposing_counsel else None,
                jurisdiction=case_context.get("jurisdiction"),
                limit=self.max_precedents * 2  # Over-fetch for filtering
            )
            
            if precedents:
                # Filter and rank by relevance to opposition
                filtered = self._filter_opposing_precedents(
                    precedents,
                    our_argument,
                    case_context
                )
                
                return filtered[:self.max_precedents]
            else:
                logger.warning("No precedents found from GraphRAGRetrieval")
                return self._generate_mock_opposing_precedents(our_argument)
                    
        except Exception as e:
            logger.error(f"Error searching opposing precedents: {e}")
            # Fallback to mock data
            return self._generate_mock_opposing_precedents(our_argument)
            
    def _construct_opposing_search_query(
        self,
        our_argument: str,
        case_context: Dict[str, Any]
    ) -> str:
        """Construct search query for opposing precedents.
        
        Args:
            our_argument: Our argument
            case_context: Case context
            
        Returns:
            Search query string
        """
        # Extract key terms from our argument
        # Invert the perspective for searching
        position = case_context.get("our_role", "plaintiff")
        opposing_position = "defendant" if position == "plaintiff" else "plaintiff"
        
        query_parts = [
            f"successful {opposing_position} arguments",
            f"defeating {position} claims",
            case_context.get("case_type", ""),
            "prevailing party opposition"
        ]
        
        # Add specific issue if available
        if "key_issues" in case_context:
            query_parts.extend(case_context["key_issues"])
            
        return " ".join(filter(None, query_parts))
        
    def _filter_opposing_precedents(
        self,
        precedents: List[Dict[str, Any]],
        our_argument: str,
        case_context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Filter precedents for those most relevant to opposition.
        
        Args:
            precedents: List of precedent cases
            our_argument: Our argument
            case_context: Case context
            
        Returns:
            Filtered and ranked precedents
        """
        scored_precedents = []
        
        for precedent in precedents:
            score = 0.0
            
            # Check if outcome opposes our position
            outcome = precedent.get("metadata", {}).get("outcome", "")
            if self._is_opposing_outcome(outcome, case_context):
                score += self.search_strategy.get("opposite_outcome_weight", 0.8)
                
            # Check for counter-arguments
            segments = precedent.get("segments", [])
            for segment in segments:
                if "rebuttal" in segment.get("role", "").lower():
                    score += self.search_strategy.get("counter_argument_weight", 0.7)
                    
            # Check confidence score
            confidence = precedent.get("confidence", {}).get("value", 0)
            if confidence > self.confidence_threshold:
                score += confidence * 0.5
                
            if score > 0:
                scored_precedents.append((score, precedent))
                
        # Sort by score and return
        scored_precedents.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored_precedents]
        
    def _is_opposing_outcome(self, outcome: str, case_context: Dict[str, Any]) -> bool:
        """Check if outcome opposes our position.
        
        Args:
            outcome: Case outcome
            case_context: Our case context
            
        Returns:
            True if outcome opposes our position
        """
        our_role = case_context.get("our_role", "plaintiff")
        
        # Map outcomes to winning party
        if our_role == "plaintiff":
            opposing_outcomes = ["denied", "dismissed", "defendant_won", "lost"]
        else:
            opposing_outcomes = ["granted", "plaintiff_won", "won"]
            
        return any(opp in outcome.lower() for opp in opposing_outcomes)
        
    async def _identify_argument_weaknesses(
        self,
        our_argument: str,
        opposing_precedents: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """Identify weaknesses in our argument based on opposing precedents.
        
        Args:
            our_argument: Our legal argument
            opposing_precedents: Precedents that oppose our position
            
        Returns:
            List of identified weaknesses
        """
        weaknesses = []
        
        # Analyze precedents for successful counter-arguments
        for precedent in opposing_precedents:
            segments = precedent.get("segments", [])
            for segment in segments:
                if segment.get("role") in ["rebuttal", "response"]:
                    weakness = {
                        "type": "precedent_counter",
                        "description": f"Similar argument was successfully countered in {precedent.get('case', {}).get('caption', 'previous case')}",
                        "precedent_text": segment.get("text", "")[:200],
                        "citation": precedent.get("case", {}).get("caption", "")
                    }
                    weaknesses.append(weakness)
                    
        # Use AI to identify logical weaknesses
        if self.openai_client:
            try:
                prompt = f"""Identify potential weaknesses in this legal argument that opposing counsel might exploit:

Argument: {our_argument}

Based on these opposing precedents:
{json.dumps([p.get('case', {}).get('caption', '') for p in opposing_precedents[:3]], indent=2)}

List 2-3 specific weaknesses:"""

                # Use OpenAI Agent to identify logical weaknesses
                messages = [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
                
                # Run the agent
                response = await run(
                    agent=self.legal_agent,
                    messages=messages
                )
                
                # Extract weaknesses from the response
                if response.messages:
                    ai_weaknesses = response.messages[-1].content.split("\n")
                    for weakness_text in ai_weaknesses:
                        if weakness_text.strip():
                            weaknesses.append({
                                "type": "logical_weakness",
                                "description": weakness_text.strip()
                            })
                        
            except Exception as e:
                logger.error(f"Error identifying weaknesses with AI: {e}")
                
        return weaknesses[:5]  # Limit to top 5 weaknesses
        
    async def _generate_opposing_response(
        self,
        our_argument: str,
        opposing_precedents: List[Dict[str, Any]],
        weaknesses: List[Dict[str, str]],
        case_context: Dict[str, Any],
        opposing_counsel: Optional[LawyerInfo] = None
    ) -> Dict[str, Any]:
        """Generate the opposing counsel's response.
        
        Args:
            our_argument: Our argument
            opposing_precedents: Supporting precedents for opposition
            weaknesses: Identified weaknesses in our argument
            case_context: Case context
            opposing_counsel: Opposing counsel info
            
        Returns:
            Generated opposing response
        """
        try:
            # Prepare precedent summaries
            precedent_summaries = []
            citations = []
            for p in opposing_precedents[:3]:
                case_info = p.get("case", {})
                caption = case_info.get("caption", "Unknown Case")
                precedent_summaries.append(f"- {caption}: {p.get('segments', [{}])[0].get('text', '')[:150]}...")
                citations.append(caption)
                
            # Prepare weakness summaries
            weakness_summaries = [w["description"] for w in weaknesses[:3]]
            
            # Generate response using AI
            counsel_name = opposing_counsel.name if opposing_counsel else "Opposing Counsel"
            counsel_style = self._get_counsel_style(opposing_counsel)
            
            prompt = f"""You are {counsel_name}, an experienced {counsel_style} lawyer representing the {'defendant' if case_context.get('our_role') == 'plaintiff' else 'plaintiff'}.

Generate a strong legal response to counter this argument from opposing counsel:
"{our_argument}"

Use these supporting precedents:
{chr(10).join(precedent_summaries)}

Exploit these identified weaknesses:
{chr(10).join(weakness_summaries)}

Case context: {case_context.get('case_type', 'civil litigation')} in {case_context.get('court', 'court')}

Provide a compelling counter-argument that:
1. Directly challenges the opposing position
2. Cites relevant precedents
3. Exploits the identified weaknesses
4. Maintains professional legal tone

Response (2-3 paragraphs):"""

            # Create a specialized opposing counsel agent
            opposing_agent = Agent(
                name=f"Opposing Counsel - {counsel_name}",
                model="gpt-4-turbo-preview",
                instructions=f"You are {counsel_name}, an experienced {counsel_style} lawyer. You respond as opposing counsel with strong legal arguments based on precedents and exploit weaknesses in the opposing position."
            )
            
            messages = [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            # Run the opposing counsel agent
            response = await run(
                agent=opposing_agent,
                messages=messages
            )
            
            generated_argument = response.messages[-1].content if response.messages else "The opposing party's argument lacks merit."
            
            # Calculate confidence based on precedents and weaknesses
            confidence = self._calculate_response_confidence(
                opposing_precedents,
                weaknesses
            )
            
            return {
                "argument": generated_argument,
                "citations": citations,
                "confidence": confidence,
                "counsel_style": counsel_style
            }
            
        except Exception as e:
            logger.error(f"Error generating opposing response: {e}")
            # Fallback response
            return {
                "argument": "The opposing party's argument lacks merit and is contradicted by established precedent. We maintain our position based on the clear application of law to the facts at hand.",
                "citations": [],
                "confidence": 0.5,
                "counsel_style": "standard"
            }
            
    def _get_counsel_style(self, opposing_counsel: Optional[LawyerInfo]) -> str:
        """Determine opposing counsel's style based on their profile.
        
        Args:
            opposing_counsel: Opposing counsel info
            
        Returns:
            Style descriptor
        """
        if not opposing_counsel:
            return "professional"
            
        # Based on experience and specializations
        if opposing_counsel.years_experience and opposing_counsel.years_experience > 15:
            return "seasoned and aggressive"
        elif opposing_counsel.win_rate and opposing_counsel.win_rate > 0.7:
            return "highly successful and methodical"
        elif "litigation" in str(opposing_counsel.specializations).lower():
            return "experienced trial"
        else:
            return "competent"
            
    def _calculate_response_confidence(
        self,
        precedents: List[Dict[str, Any]],
        weaknesses: List[Dict[str, str]]
    ) -> float:
        """Calculate confidence score for the opposing response.
        
        Args:
            precedents: Supporting precedents
            weaknesses: Identified weaknesses
            
        Returns:
            Confidence score between 0 and 1
        """
        base_confidence = 0.5
        
        # Add confidence for precedents
        precedent_boost = min(len(precedents) * 0.1, 0.3)
        
        # Add confidence for weaknesses
        weakness_boost = min(len(weaknesses) * 0.05, 0.15)
        
        # Average precedent confidence scores
        if precedents:
            avg_precedent_confidence = sum(
                p.get("confidence", {}).get("value", 0) 
                for p in precedents
            ) / len(precedents)
            precedent_confidence_boost = avg_precedent_confidence * 0.2
        else:
            precedent_confidence_boost = 0
            
        total_confidence = base_confidence + precedent_boost + weakness_boost + precedent_confidence_boost
        return min(total_confidence, 0.95)  # Cap at 95%
        
    def _assess_response_strength(
        self,
        response: Dict[str, Any],
        precedents: List[Dict[str, Any]],
        weaknesses: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Assess the strength of the opposing response.
        
        Args:
            response: Generated response
            precedents: Supporting precedents
            weaknesses: Identified weaknesses
            
        Returns:
            Strength assessment
        """
        strength_factors = {
            "precedent_support": min(len(precedents) / self.max_precedents, 1.0),
            "weakness_exploitation": min(len(weaknesses) / 3, 1.0),
            "citation_strength": min(len(response["citations"]) / 5, 1.0),
            "confidence": response["confidence"]
        }
        
        overall_strength = sum(strength_factors.values()) / len(strength_factors)
        
        # Determine strength level
        if overall_strength > 0.8:
            level = "very_strong"
            description = "The opposing argument is very strong and well-supported"
        elif overall_strength > 0.6:
            level = "strong"
            description = "The opposing argument is strong with good precedent support"
        elif overall_strength > 0.4:
            level = "moderate"
            description = "The opposing argument has moderate strength"
        else:
            level = "weak"
            description = "The opposing argument has identifiable weaknesses"
            
        return {
            "level": level,
            "score": round(overall_strength, 2),
            "description": description,
            "factors": strength_factors,
            "recommendations": self._get_strength_recommendations(level)
        }
        
    def _get_strength_recommendations(self, strength_level: str) -> List[str]:
        """Get recommendations based on opposing argument strength.
        
        Args:
            strength_level: Strength level of opposing argument
            
        Returns:
            List of recommendations
        """
        recommendations = {
            "very_strong": [
                "Consider settlement negotiations",
                "Prepare comprehensive counter-precedents",
                "Focus on distinguishing facts",
                "Strengthen procedural arguments"
            ],
            "strong": [
                "Develop strong counter-arguments",
                "Research additional supporting cases",
                "Prepare witness testimony to support position"
            ],
            "moderate": [
                "Maintain current strategy with refinements",
                "Identify and exploit remaining weaknesses",
                "Strengthen citation support"
            ],
            "weak": [
                "Press advantage aggressively",
                "File motion for summary judgment if applicable",
                "Highlight weaknesses in oral arguments"
            ]
        }
        
        return recommendations.get(strength_level, ["Continue with planned strategy"])
        
    async def _generate_counter_arguments(
        self,
        opposing_argument: str,
        our_original_argument: str,
        case_context: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Generate counter-arguments to the opposing response.
        
        Args:
            opposing_argument: The opposing counsel's argument
            our_original_argument: Our original argument
            case_context: Case context
            
        Returns:
            List of suggested counter-arguments
        """
        try:
            prompt = f"""As legal counsel, suggest 3 strong counter-arguments to this opposing argument:

Opposing Argument:
{opposing_argument}

Our Original Position:
{our_original_argument}

Case Type: {case_context.get('case_type', 'litigation')}
Court: {case_context.get('court', 'court')}

Provide 3 concise counter-arguments that:
1. Address the opposing points directly
2. Reinforce our original position
3. Cite legal principles or precedents where relevant

Format each as a brief 2-3 sentence counter-argument."""

            # Create counter-argument agent
            counter_agent = Agent(
                name="Counter Argument Strategist",
                model="gpt-4-turbo-preview",
                instructions="You are an expert legal strategist providing strong counter-arguments to opposing counsel's positions."
            )
            
            messages = [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            # Run the counter-argument agent
            response = await run(
                agent=counter_agent,
                messages=messages
            )
            
            counter_text = response.messages[-1].content if response.messages else ""
            counters = []
            
            # Parse the response into individual counter-arguments
            parts = counter_text.split("\n\n")
            for i, part in enumerate(parts[:3], 1):
                if part.strip():
                    counters.append({
                        "id": f"counter_{i}",
                        "text": part.strip(),
                        "strength": "high" if i == 1 else "medium"
                    })
                    
            return counters
            
        except Exception as e:
            logger.error(f"Error generating counter-arguments: {e}")
            # Fallback counters
            return [
                {
                    "id": "counter_1",
                    "text": "The opposing counsel's interpretation misapplies the relevant legal standard and ignores key factual distinctions.",
                    "strength": "medium"
                },
                {
                    "id": "counter_2",
                    "text": "The cited precedents are distinguishable on their facts and do not support the opposition's position.",
                    "strength": "medium"
                }
            ]
            
    def _generate_mock_opposing_precedents(self, our_argument: str) -> List[Dict[str, Any]]:
        """Generate mock opposing precedents for demo purposes.
        
        Args:
            our_argument: Our legal argument
            
        Returns:
            List of mock precedents
        """
        mock_precedents = [
            {
                "argument_id": "opp_mock_001",
                "confidence": {"value": 0.82},
                "case": {
                    "caption": "Smith v. Johnson Corp",
                    "court": "Court of Appeals",
                    "outcome": "defendant_won"
                },
                "segments": [{
                    "text": "The court finds that the plaintiff's claims are without merit due to lack of substantive evidence and failure to establish causation.",
                    "role": "rebuttal"
                }],
                "metadata": {"outcome": "denied"}
            },
            {
                "argument_id": "opp_mock_002",
                "confidence": {"value": 0.75},
                "case": {
                    "caption": "State v. Williams",
                    "court": "Supreme Court",
                    "outcome": "dismissed"
                },
                "segments": [{
                    "text": "The defendant successfully demonstrated that the plaintiff's interpretation of the statute is inconsistent with legislative intent.",
                    "role": "response"
                }],
                "metadata": {"outcome": "dismissed"}
            }
        ]
        
        return mock_precedents