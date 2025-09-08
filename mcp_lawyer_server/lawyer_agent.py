"""Lawyer agent implementation for conversational legal assistance."""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import httpx
import openai
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
import json

from .legal_context import LegalContext, ArgumentContext, LawyerInfo, CaseInfo
from .opponent_simulator import OpponentSimulator

logger = structlog.get_logger()


class LawyerAgent:
    """AI-powered lawyer agent for legal consultation and case analysis."""
    
    def __init__(
        self,
        graphrag_base_url: str,
        openai_api_key: str,
        openai_model: str = "gpt-4-turbo-preview",
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize lawyer agent.
        
        Args:
            graphrag_base_url: Base URL for GraphRAG API
            openai_api_key: OpenAI API key
            openai_model: OpenAI model to use
            config: Optional configuration dictionary
        """
        self.graphrag_base_url = graphrag_base_url
        self.openai_client = openai.AsyncOpenAI(api_key=openai_api_key)
        self.openai_model = openai_model
        self.config = config or {}
        
        # Initialize opponent simulator
        self.opponent_simulator = OpponentSimulator(
            graphrag_base_url=graphrag_base_url,
            openai_client=self.openai_client,
            config=config.get("opponent_simulation", {})
        )
        
        # Cache for precedents
        self._precedent_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_ttl = 600  # 10 minutes
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def consult(
        self,
        query: str,
        context: LegalContext,
        include_precedents: bool = True,
        simulate_opposition: bool = False
    ) -> Dict[str, Any]:
        """Main consultation interface for legal queries.
        
        Args:
            query: User's legal question or argument
            context: Legal context for the session
            include_precedents: Whether to include precedent search
            simulate_opposition: Whether to simulate opposing counsel's response
            
        Returns:
            Consultation response with legal advice and analysis
        """
        try:
            # 1. Retrieve relevant precedents if requested
            precedents = []
            if include_precedents:
                precedents = await self._retrieve_precedents(query, context)
                
            # 2. Generate lawyer's response
            lawyer_response = await self._generate_lawyer_response(
                query,
                context,
                precedents
            )
            
            # 3. Create argument context
            argument_context = ArgumentContext(
                argument_id=self._generate_argument_id(),
                text=lawyer_response["argument"],
                supporting_precedents=[p.get("case", {}).get("caption", "") for p in precedents[:3]],
                citations=lawyer_response["citations"],
                confidence=lawyer_response["confidence"]
            )
            
            # 4. Add to context
            context.add_our_argument(argument_context)
            
            # 5. Simulate opposition if requested
            opposition_analysis = None
            if simulate_opposition and context.opposing_counsel:
                opposition_analysis = await self.opponent_simulator.simulate_opponent_response(
                    our_argument=lawyer_response["argument"],
                    case_context=context.case_info.to_dict() if context.case_info else {},
                    opposing_counsel=context.opposing_counsel,
                    our_position=context.case_info.our_role.value if context.case_info and context.case_info.our_role else None
                )
                
                # Add to context
                if opposition_analysis:
                    opp_context = ArgumentContext(
                        argument_id=self._generate_argument_id("opp"),
                        text=opposition_analysis["opposing_argument"],
                        supporting_precedents=opposition_analysis.get("supporting_precedents", []),
                        citations=opposition_analysis.get("citations", []),
                        confidence=opposition_analysis.get("confidence", 0),
                        weaknesses=opposition_analysis.get("identified_weaknesses", []),
                        counter_arguments=[c["text"] for c in opposition_analysis.get("suggested_counters", [])]
                    )
                    context.add_anticipated_opposition(opp_context)
                    
            # 6. Compile comprehensive response
            response = {
                "lawyer_response": {
                    "argument": lawyer_response["argument"],
                    "explanation": lawyer_response["explanation"],
                    "citations": lawyer_response["citations"],
                    "confidence": lawyer_response["confidence"],
                    "precedents_used": precedents[:3] if precedents else [],
                    "key_points": lawyer_response["key_points"]
                },
                "opposition_analysis": opposition_analysis,
                "recommendations": await self._generate_recommendations(
                    lawyer_response,
                    opposition_analysis,
                    context
                ),
                "next_steps": self._suggest_next_steps(
                    context,
                    lawyer_response["confidence"],
                    opposition_analysis
                ),
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "session_id": context.session_id,
                    "turn_number": len(context.conversation_history) + 1,
                    "precedents_searched": len(precedents),
                    "opposition_simulated": simulate_opposition
                }
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Error in lawyer consultation: {e}")
            raise
            
    async def _retrieve_precedents(
        self,
        query: str,
        context: LegalContext
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant precedents from GraphRAG.
        
        Args:
            query: Search query
            context: Legal context
            
        Returns:
            List of relevant precedents
        """
        # Check cache first
        cache_key = f"{query}_{context.our_lawyer.id if context.our_lawyer else 'default'}"
        if cache_key in self._precedent_cache:
            cached_data, cache_time = self._precedent_cache[cache_key]
            if (datetime.now() - cache_time).total_seconds() < self._cache_ttl:
                logger.info(f"Using cached precedents for query: {query[:50]}...")
                return cached_data
                
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.graphrag_base_url}/api/v1/retrieval/past-defenses",
                    json={
                        "issue_text": query,
                        "lawyer_id": context.our_lawyer.id if context.our_lawyer else None,
                        "jurisdiction": context.case_info.jurisdiction if context.case_info else None,
                        "limit": 10
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    precedents = data.get("bundles", [])
                    
                    # Cache the results
                    self._precedent_cache[cache_key] = (precedents, datetime.now())
                    
                    # Add to context
                    for p in precedents[:5]:
                        context.add_precedent({
                            "case": p.get("case", {}),
                            "confidence": p.get("confidence", {}),
                            "issue": p.get("issue", {})
                        })
                        
                    return precedents
                else:
                    logger.warning(f"GraphRAG API returned {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error retrieving precedents: {e}")
            # Return mock precedents for demo
            return self._generate_mock_precedents(query)
            
    async def _generate_lawyer_response(
        self,
        query: str,
        context: LegalContext,
        precedents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate lawyer's response using AI.
        
        Args:
            query: User's query
            context: Legal context
            precedents: Retrieved precedents
            
        Returns:
            Generated response with analysis
        """
        try:
            # Prepare context information
            case_summary = self._prepare_case_summary(context)
            precedent_summary = self._prepare_precedent_summary(precedents)
            history_summary = self._prepare_history_summary(context)
            
            # Construct prompt
            lawyer_name = context.our_lawyer.name if context.our_lawyer else "Legal Counsel"
            lawyer_firm = context.our_lawyer.firm if context.our_lawyer and context.our_lawyer.firm else "Law Firm"
            
            system_prompt = f"""You are {lawyer_name}, an experienced lawyer at {lawyer_firm} specializing in legal analysis and litigation strategy. 
You provide thorough, professional legal advice based on precedents and case law.
You always cite relevant cases and legal principles to support your arguments."""

            user_prompt = f"""Client Query: {query}

Case Context:
{case_summary}

Recent Conversation:
{history_summary}

Relevant Precedents:
{precedent_summary}

Please provide:
1. A comprehensive legal response addressing the query
2. Cite specific precedents and legal principles
3. Identify key strategic points
4. Explain the reasoning clearly
5. Assess confidence level (0-1) based on precedent support

Format your response with clear sections."""

            response = await self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=1500
            )
            
            response_text = response.choices[0].message.content
            
            # Parse the response
            parsed_response = self._parse_lawyer_response(response_text, precedents)
            
            return parsed_response
            
        except Exception as e:
            logger.error(f"Error generating lawyer response: {e}")
            # Fallback response
            return {
                "argument": "Based on the information provided, I recommend we proceed cautiously while gathering additional evidence to support our position.",
                "explanation": "Further analysis is required to provide comprehensive legal advice.",
                "citations": [],
                "confidence": 0.5,
                "key_points": ["Gather additional evidence", "Research relevant precedents", "Assess procedural options"]
            }
            
    def _prepare_case_summary(self, context: LegalContext) -> str:
        """Prepare case summary for AI prompt.
        
        Args:
            context: Legal context
            
        Returns:
            Case summary string
        """
        if not context.case_info:
            return "No specific case information provided."
            
        case = context.case_info
        summary = f"""
Case: {case.caption}
Court: {case.court}
Jurisdiction: {case.jurisdiction}
Type: {case.case_type}
Our Role: {case.our_role.value if case.our_role else 'Not specified'}
Judge: {case.judge_name or 'Not assigned'}
Current Stage: {case.current_stage or 'Initial'}
Key Issues: {', '.join(case.key_issues) if case.key_issues else 'To be determined'}
"""
        return summary.strip()
        
    def _prepare_precedent_summary(self, precedents: List[Dict[str, Any]]) -> str:
        """Prepare precedent summary for AI prompt.
        
        Args:
            precedents: List of precedents
            
        Returns:
            Precedent summary string
        """
        if not precedents:
            return "No directly relevant precedents found in initial search."
            
        summaries = []
        for i, p in enumerate(precedents[:5], 1):
            case = p.get("case", {})
            segments = p.get("segments", [])
            confidence = p.get("confidence", {}).get("value", 0)
            
            summary = f"""{i}. {case.get('caption', 'Unknown Case')} ({case.get('court', 'Court')})
   Confidence: {confidence:.2f}
   Key Argument: {segments[0].get('text', 'No text available')[:200] if segments else 'No argument text'}..."""
            summaries.append(summary)
            
        return "\n\n".join(summaries)
        
    def _prepare_history_summary(self, context: LegalContext) -> str:
        """Prepare conversation history summary.
        
        Args:
            context: Legal context
            
        Returns:
            History summary string
        """
        recent_turns = context.get_recent_history(5)
        if not recent_turns:
            return "This is the beginning of our consultation."
            
        summaries = []
        for turn in recent_turns[-3:]:  # Last 3 turns
            role = turn.role.capitalize()
            message = turn.message[:200] + "..." if len(turn.message) > 200 else turn.message
            summaries.append(f"{role}: {message}")
            
        return "\n".join(summaries)
        
    def _parse_lawyer_response(
        self,
        response_text: str,
        precedents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Parse AI response into structured format.
        
        Args:
            response_text: Raw AI response
            precedents: Available precedents
            
        Returns:
            Parsed response dictionary
        """
        # Extract main argument (first substantial paragraph)
        lines = response_text.split("\n")
        argument_lines = []
        explanation_lines = []
        key_points = []
        citations = []
        
        current_section = "argument"
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Detect section headers
            if any(keyword in line.lower() for keyword in ["explanation:", "reasoning:", "analysis:"]):
                current_section = "explanation"
                continue
            elif any(keyword in line.lower() for keyword in ["key points:", "strategic points:", "summary:"]):
                current_section = "key_points"
                continue
            elif any(keyword in line.lower() for keyword in ["citations:", "cases cited:", "precedents:"]):
                current_section = "citations"
                continue
            elif any(keyword in line.lower() for keyword in ["confidence:", "assessment:"]):
                current_section = "confidence"
                continue
                
            # Add to appropriate section
            if current_section == "argument" and len(argument_lines) < 5:
                argument_lines.append(line)
            elif current_section == "explanation":
                explanation_lines.append(line)
            elif current_section == "key_points" and line.startswith(("-", "•", "*", "1", "2", "3")):
                # Clean up bullet points
                point = line.lstrip("-•*123456789. ")
                if point:
                    key_points.append(point)
            elif current_section == "citations":
                if "v." in line or "v " in line:  # Likely a case citation
                    citations.append(line)
                    
        # Extract confidence value
        confidence = 0.75  # Default
        confidence_match = None
        for line in lines:
            if "confidence" in line.lower():
                # Try to extract a number
                import re
                numbers = re.findall(r"0\.\d+|\d+%", line)
                if numbers:
                    conf_str = numbers[0].replace("%", "")
                    try:
                        conf_val = float(conf_str)
                        confidence = conf_val / 100 if conf_val > 1 else conf_val
                    except:
                        pass
                        
        # Add precedent citations
        for p in precedents[:3]:
            case_caption = p.get("case", {}).get("caption", "")
            if case_caption and case_caption not in citations:
                citations.append(case_caption)
                
        return {
            "argument": " ".join(argument_lines) or response_text[:500],
            "explanation": " ".join(explanation_lines) or "Legal analysis based on applicable law and precedents.",
            "citations": citations[:5],
            "confidence": min(confidence, 0.95),
            "key_points": key_points[:5] if key_points else self._extract_default_key_points(response_text)
        }
        
    def _extract_default_key_points(self, text: str) -> List[str]:
        """Extract default key points from text.
        
        Args:
            text: Response text
            
        Returns:
            List of key points
        """
        # Simple extraction of key sentences
        sentences = text.split(".")
        key_points = []
        
        keywords = ["must", "should", "recommend", "important", "critical", "essential"]
        for sentence in sentences[:10]:
            if any(keyword in sentence.lower() for keyword in keywords):
                point = sentence.strip()
                if 20 < len(point) < 150:  # Reasonable length
                    key_points.append(point)
                    if len(key_points) >= 3:
                        break
                        
        return key_points or ["Proceed with comprehensive legal analysis", "Gather supporting evidence", "Consider all strategic options"]
        
    async def _generate_recommendations(
        self,
        lawyer_response: Dict[str, Any],
        opposition_analysis: Optional[Dict[str, Any]],
        context: LegalContext
    ) -> List[Dict[str, str]]:
        """Generate strategic recommendations.
        
        Args:
            lawyer_response: Lawyer's response
            opposition_analysis: Opposition analysis if available
            context: Legal context
            
        Returns:
            List of recommendations
        """
        recommendations = []
        
        # Based on confidence level
        confidence = lawyer_response["confidence"]
        if confidence > 0.8:
            recommendations.append({
                "type": "strategy",
                "priority": "high",
                "text": "Strong legal position - consider aggressive litigation strategy"
            })
        elif confidence > 0.6:
            recommendations.append({
                "type": "strategy",
                "priority": "medium",
                "text": "Moderate position - focus on strengthening key arguments with additional precedents"
            })
        else:
            recommendations.append({
                "type": "strategy",
                "priority": "high",
                "text": "Position needs strengthening - consider alternative legal theories or settlement"
            })
            
        # Based on opposition analysis
        if opposition_analysis:
            strength = opposition_analysis.get("strength_assessment", {})
            if strength.get("level") == "very_strong":
                recommendations.append({
                    "type": "defense",
                    "priority": "high",
                    "text": "Prepare robust counter-arguments to anticipated strong opposition"
                })
            elif strength.get("level") == "weak":
                recommendations.append({
                    "type": "offense",
                    "priority": "medium",
                    "text": "Opposition appears vulnerable - press advantage with motion practice"
                })
                
        # Procedural recommendations
        if context.case_info and context.case_info.current_stage:
            stage = context.case_info.current_stage
            if "motion" in stage.lower():
                recommendations.append({
                    "type": "procedural",
                    "priority": "high",
                    "text": "Prepare comprehensive motion briefing with supporting declarations"
                })
            elif "discovery" in stage.lower():
                recommendations.append({
                    "type": "procedural",
                    "priority": "medium",
                    "text": "Focus on discovery to uncover supporting evidence"
                })
                
        return recommendations[:5]  # Limit to top 5
        
    def _suggest_next_steps(
        self,
        context: LegalContext,
        confidence: float,
        opposition_analysis: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Suggest next steps based on analysis.
        
        Args:
            context: Legal context
            confidence: Confidence level
            opposition_analysis: Opposition analysis
            
        Returns:
            List of suggested next steps
        """
        next_steps = []
        
        # Based on confidence
        if confidence < 0.6:
            next_steps.append("Research additional supporting precedents")
            next_steps.append("Consider expert witness consultation")
            
        # Based on opposition
        if opposition_analysis:
            if opposition_analysis.get("identified_weaknesses"):
                next_steps.append("Address identified weaknesses in our argument")
            if opposition_analysis.get("suggested_counters"):
                next_steps.append("Prepare counter-arguments to anticipated opposition")
                
        # Based on case stage
        if context.case_info:
            if not context.case_info.current_stage:
                next_steps.append("File initial pleadings")
            elif "discovery" in str(context.case_info.current_stage).lower():
                next_steps.append("Serve discovery requests")
                next_steps.append("Prepare witness depositions")
                
        # Always include
        next_steps.append("Schedule follow-up consultation to refine strategy")
        
        return next_steps[:5]
        
    async def analyze_case(
        self,
        context: LegalContext,
        deep_analysis: bool = True
    ) -> Dict[str, Any]:
        """Perform deep case analysis.
        
        Args:
            context: Legal context
            deep_analysis: Whether to perform deep analysis
            
        Returns:
            Case analysis results
        """
        try:
            # Gather all arguments from context
            our_args = context.our_arguments
            opp_args = context.anticipated_oppositions
            
            # Retrieve comprehensive precedents
            all_precedents = []
            if context.case_info:
                for issue in context.case_info.key_issues[:3]:
                    precedents = await self._retrieve_precedents(issue, context)
                    all_precedents.extend(precedents)
                    
            # Perform analysis
            analysis = {
                "case_strength": self._assess_case_strength(our_args, opp_args, all_precedents),
                "key_legal_issues": self._identify_key_issues(context, all_precedents),
                "precedent_analysis": self._analyze_precedents(all_precedents),
                "risk_assessment": self._assess_risks(context, our_args, opp_args),
                "strategic_options": self._identify_strategic_options(context, analysis),
                "timeline_projection": self._project_timeline(context),
                "success_probability": self._calculate_success_probability(
                    our_args, opp_args, all_precedents
                )
            }
            
            if deep_analysis:
                # Add detailed analysis
                analysis["detailed_argument_analysis"] = await self._deep_argument_analysis(
                    our_args, context
                )
                analysis["opposition_vulnerability"] = self._analyze_opposition_vulnerabilities(
                    opp_args
                )
                
            return analysis
            
        except Exception as e:
            logger.error(f"Error in case analysis: {e}")
            return {
                "error": "Analysis unavailable",
                "message": str(e)
            }
            
    def _assess_case_strength(
        self,
        our_args: List[ArgumentContext],
        opp_args: List[ArgumentContext],
        precedents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Assess overall case strength.
        
        Args:
            our_args: Our arguments
            opp_args: Opposition arguments
            precedents: Available precedents
            
        Returns:
            Case strength assessment
        """
        # Calculate average confidence
        our_confidence = sum(arg.confidence for arg in our_args) / len(our_args) if our_args else 0.5
        opp_confidence = sum(arg.confidence for arg in opp_args) / len(opp_args) if opp_args else 0.3
        
        # Precedent support
        precedent_support = min(len(precedents) / 10, 1.0)
        
        # Overall strength
        overall_strength = (our_confidence * 0.5 + precedent_support * 0.3 + (1 - opp_confidence) * 0.2)
        
        return {
            "overall_strength": round(overall_strength, 2),
            "our_position_strength": round(our_confidence, 2),
            "opposition_strength": round(opp_confidence, 2),
            "precedent_support": round(precedent_support, 2),
            "assessment": self._get_strength_label(overall_strength)
        }
        
    def _get_strength_label(self, strength: float) -> str:
        """Get strength label from score.
        
        Args:
            strength: Strength score
            
        Returns:
            Strength label
        """
        if strength > 0.8:
            return "Very Strong"
        elif strength > 0.6:
            return "Strong"
        elif strength > 0.4:
            return "Moderate"
        elif strength > 0.2:
            return "Weak"
        else:
            return "Very Weak"
            
    def _identify_key_issues(
        self,
        context: LegalContext,
        precedents: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """Identify key legal issues.
        
        Args:
            context: Legal context
            precedents: Available precedents
            
        Returns:
            List of key issues
        """
        issues = []
        
        # From case info
        if context.case_info and context.case_info.key_issues:
            for issue in context.case_info.key_issues:
                issues.append({
                    "issue": issue,
                    "type": "primary",
                    "source": "case_filing"
                })
                
        # From precedents
        issue_map = {}
        for p in precedents:
            issue = p.get("issue", {})
            if issue.get("title"):
                title = issue["title"]
                if title not in issue_map:
                    issue_map[title] = 0
                issue_map[title] += 1
                
        # Add frequently appearing issues
        for issue_title, count in sorted(issue_map.items(), key=lambda x: x[1], reverse=True)[:3]:
            issues.append({
                "issue": issue_title,
                "type": "related",
                "source": f"precedents ({count} cases)"
            })
            
        return issues[:5]
        
    def _analyze_precedents(self, precedents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze precedent patterns.
        
        Args:
            precedents: List of precedents
            
        Returns:
            Precedent analysis
        """
        if not precedents:
            return {
                "total_precedents": 0,
                "average_confidence": 0,
                "outcome_distribution": {},
                "top_citations": []
            }
            
        # Outcome distribution
        outcomes = {}
        citations = {}
        total_confidence = 0
        
        for p in precedents:
            # Outcome
            outcome = p.get("metadata", {}).get("outcome", "unknown")
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            
            # Confidence
            confidence = p.get("confidence", {}).get("value", 0)
            total_confidence += confidence
            
            # Citations
            for segment in p.get("segments", []):
                for citation in segment.get("citations", []):
                    citations[citation] = citations.get(citation, 0) + 1
                    
        return {
            "total_precedents": len(precedents),
            "average_confidence": round(total_confidence / len(precedents), 2),
            "outcome_distribution": outcomes,
            "top_citations": sorted(citations.items(), key=lambda x: x[1], reverse=True)[:5]
        }
        
    def _assess_risks(
        self,
        context: LegalContext,
        our_args: List[ArgumentContext],
        opp_args: List[ArgumentContext]
    ) -> List[Dict[str, str]]:
        """Assess case risks.
        
        Args:
            context: Legal context
            our_args: Our arguments
            opp_args: Opposition arguments
            
        Returns:
            List of identified risks
        """
        risks = []
        
        # Weakness-based risks
        for arg in our_args:
            if arg.weaknesses:
                risks.append({
                    "type": "argument_weakness",
                    "severity": "high" if len(arg.weaknesses) > 2 else "medium",
                    "description": f"Argument has {len(arg.weaknesses)} identified weaknesses",
                    "mitigation": "Strengthen with additional precedents or alternative theories"
                })
                
        # Opposition strength risks
        for arg in opp_args:
            if arg.confidence > 0.8:
                risks.append({
                    "type": "strong_opposition",
                    "severity": "high",
                    "description": f"Opposition has high-confidence counter-argument ({arg.confidence:.2f})",
                    "mitigation": "Prepare detailed rebuttal with distinguishing factors"
                })
                
        # Procedural risks
        if context.case_info and context.case_info.upcoming_deadlines:
            for deadline_name, deadline_date in context.case_info.upcoming_deadlines.items():
                days_until = (deadline_date - datetime.now()).days
                if days_until < 7:
                    risks.append({
                        "type": "deadline",
                        "severity": "critical" if days_until < 3 else "high",
                        "description": f"{deadline_name} deadline in {days_until} days",
                        "mitigation": "Prioritize preparation and filing"
                    })
                    
        return risks[:5]
        
    def _identify_strategic_options(
        self,
        context: LegalContext,
        analysis: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Identify strategic options.
        
        Args:
            context: Legal context
            analysis: Current analysis
            
        Returns:
            List of strategic options
        """
        options = []
        
        # Based on case strength
        strength = analysis.get("case_strength", {}).get("overall_strength", 0.5)
        
        if strength > 0.7:
            options.append({
                "option": "Aggressive Litigation",
                "description": "Push for early motion practice and summary judgment",
                "confidence": "high"
            })
        elif strength > 0.5:
            options.append({
                "option": "Standard Litigation",
                "description": "Proceed through normal discovery and motion practice",
                "confidence": "medium"
            })
        else:
            options.append({
                "option": "Settlement Negotiation",
                "description": "Explore settlement options to minimize risk",
                "confidence": "recommended"
            })
            
        # Always include
        options.append({
            "option": "Discovery Focus",
            "description": "Intensive discovery to uncover supporting evidence",
            "confidence": "medium"
        })
        
        options.append({
            "option": "Expert Witnesses",
            "description": "Retain expert witnesses to strengthen technical arguments",
            "confidence": "medium"
        })
        
        return options
        
    def _project_timeline(self, context: LegalContext) -> Dict[str, Any]:
        """Project case timeline.
        
        Args:
            context: Legal context
            
        Returns:
            Timeline projection
        """
        if not context.case_info:
            return {
                "estimated_duration": "6-12 months",
                "next_milestone": "Case filing",
                "critical_dates": []
            }
            
        stage = context.case_info.current_stage or "initial"
        
        timeline_map = {
            "initial": "12-18 months",
            "discovery": "9-12 months",
            "motion": "6-9 months",
            "trial": "3-6 months",
            "appeal": "6-12 months"
        }
        
        duration = timeline_map.get(stage.lower(), "9-12 months")
        
        return {
            "estimated_duration": duration,
            "current_stage": stage,
            "next_milestone": self._get_next_milestone(stage),
            "critical_dates": list(context.case_info.upcoming_deadlines.items()) if context.case_info.upcoming_deadlines else []
        }
        
    def _get_next_milestone(self, current_stage: str) -> str:
        """Get next milestone based on current stage.
        
        Args:
            current_stage: Current case stage
            
        Returns:
            Next milestone
        """
        milestones = {
            "initial": "File complaint/answer",
            "discovery": "Complete depositions",
            "motion": "Motion hearing",
            "trial": "Trial date",
            "appeal": "Appellate briefing"
        }
        
        return milestones.get(current_stage.lower(), "Next procedural step")
        
    def _calculate_success_probability(
        self,
        our_args: List[ArgumentContext],
        opp_args: List[ArgumentContext],
        precedents: List[Dict[str, Any]]
    ) -> float:
        """Calculate success probability.
        
        Args:
            our_args: Our arguments
            opp_args: Opposition arguments
            precedents: Available precedents
            
        Returns:
            Success probability (0-1)
        """
        factors = []
        
        # Argument strength
        if our_args:
            avg_confidence = sum(arg.confidence for arg in our_args) / len(our_args)
            factors.append(avg_confidence)
            
        # Opposition weakness
        if opp_args:
            avg_opp_confidence = sum(arg.confidence for arg in opp_args) / len(opp_args)
            factors.append(1 - avg_opp_confidence)
        else:
            factors.append(0.6)  # No known opposition
            
        # Precedent support
        if precedents:
            # Check favorable outcomes
            favorable = sum(1 for p in precedents if "won" in str(p.get("metadata", {}).get("outcome", "")).lower())
            factors.append(favorable / len(precedents) if precedents else 0.5)
            
        # Average all factors
        probability = sum(factors) / len(factors) if factors else 0.5
        
        return round(min(max(probability, 0.1), 0.9), 2)  # Cap between 10% and 90%
        
    async def _deep_argument_analysis(
        self,
        arguments: List[ArgumentContext],
        context: LegalContext
    ) -> List[Dict[str, Any]]:
        """Perform deep analysis of arguments.
        
        Args:
            arguments: Arguments to analyze
            context: Legal context
            
        Returns:
            Deep analysis results
        """
        analyses = []
        
        for arg in arguments[:3]:  # Analyze top 3 arguments
            analysis = {
                "argument_id": arg.argument_id,
                "summary": arg.text[:200] + "..." if len(arg.text) > 200 else arg.text,
                "strength_score": arg.confidence,
                "supporting_precedents": len(arg.supporting_precedents),
                "citations": len(arg.citations),
                "identified_weaknesses": len(arg.weaknesses),
                "counter_arguments_available": len(arg.counter_arguments),
                "recommendations": []
            }
            
            # Generate recommendations
            if arg.confidence < 0.6:
                analysis["recommendations"].append("Strengthen with additional research")
            if arg.weaknesses:
                analysis["recommendations"].append("Address identified weaknesses")
            if not arg.citations:
                analysis["recommendations"].append("Add supporting citations")
                
            analyses.append(analysis)
            
        return analyses
        
    def _analyze_opposition_vulnerabilities(
        self,
        opp_args: List[ArgumentContext]
    ) -> List[Dict[str, str]]:
        """Analyze opposition vulnerabilities.
        
        Args:
            opp_args: Opposition arguments
            
        Returns:
            List of vulnerabilities
        """
        vulnerabilities = []
        
        for arg in opp_args:
            if arg.confidence < 0.6:
                vulnerabilities.append({
                    "type": "weak_argument",
                    "description": f"Opposition argument has low confidence ({arg.confidence:.2f})",
                    "exploitation": "Attack this weak point aggressively"
                })
                
            if not arg.citations:
                vulnerabilities.append({
                    "type": "lack_of_support",
                    "description": "Opposition argument lacks citations",
                    "exploitation": "Challenge the legal basis"
                })
                
            if arg.weaknesses:
                vulnerabilities.append({
                    "type": "known_weaknesses",
                    "description": f"Opposition has {len(arg.weaknesses)} identified weaknesses",
                    "exploitation": "Focus cross-examination on these points"
                })
                
        return vulnerabilities[:5]
        
    def _generate_mock_precedents(self, query: str) -> List[Dict[str, Any]]:
        """Generate mock precedents for demo.
        
        Args:
            query: Search query
            
        Returns:
            List of mock precedents
        """
        return [
            {
                "argument_id": "mock_001",
                "confidence": {"value": 0.85},
                "case": {
                    "caption": "Johnson v. State Corporation",
                    "court": "Court of Appeals",
                    "jurisdiction": "CA"
                },
                "issue": {
                    "title": "Contract Interpretation",
                    "taxonomy_path": ["Contract Law", "Interpretation"]
                },
                "segments": [{
                    "text": "The court held that ambiguous contract terms must be interpreted in favor of the non-drafting party.",
                    "role": "opening",
                    "citations": ["Civil Code § 1654"]
                }],
                "metadata": {"outcome": "won"}
            }
        ]
        
    def _generate_argument_id(self, prefix: str = "arg") -> str:
        """Generate unique argument ID.
        
        Args:
            prefix: ID prefix
            
        Returns:
            Unique ID
        """
        import hashlib
        content = f"{prefix}_{datetime.now().isoformat()}"
        return hashlib.md5(content.encode()).hexdigest()[:12]