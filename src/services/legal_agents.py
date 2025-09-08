"""
Legal Agents Implementation using OpenAI Agents SDK with Orchestration via LLM
"""
from typing import Dict, List, Optional, Any, AsyncIterator
from dataclasses import dataclass
import json
import asyncio
from datetime import datetime
import logging
from openai import AsyncOpenAI
import os

logger = logging.getLogger(__name__)


@dataclass
class LegalContext:
    """Context for legal debate"""
    case_id: str
    issue_text: str
    current_turn: int = 0
    max_turns: int = 3
    messages: List[Dict[str, Any]] = None
    bundles: List[Dict[str, Any]] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.messages is None:
            self.messages = []
        if self.bundles is None:
            self.bundles = []
        if self.metadata is None:
            self.metadata = {}


class LegalAgent:
    """Base class for legal agents using OpenAI Agents SDK pattern"""
    
    def __init__(self, name: str, role: str, instructions: str, model: str = "gpt-4o-mini"):
        self.name = name
        self.role = role
        self.instructions = instructions
        self.model = model
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def run(self, messages: List[Dict[str, str]], context: Optional[LegalContext] = None) -> Dict[str, Any]:
        """
        Run the agent with given messages
        
        Args:
            messages: List of message dictionaries
            context: Optional legal context
        
        Returns:
            Agent response with content and metadata
        """
        try:
            # Build system message with dynamic context
            system_message = self._build_system_message(context)
            
            # Prepare messages for the model
            full_messages = [{"role": "system", "content": system_message}] + messages
            
            # Call OpenAI API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                temperature=0.7,
                max_tokens=1500
            )
            
            content = response.choices[0].message.content
            
            # Extract thinking process (if present in response)
            thinking = self._extract_thinking(content)
            
            return {
                "role": self.role,
                "content": content,
                "thinking": thinking,
                "agent": self.name,
                "timestamp": datetime.utcnow().isoformat(),
                "model": self.model,
                "metadata": {
                    "turn": context.current_turn if context else 0,
                    "bundles_used": len(context.bundles) if context else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Error in agent {self.name}: {e}")
            raise
    
    def _build_system_message(self, context: Optional[LegalContext]) -> str:
        """Build system message with context"""
        message = self.instructions
        
        if context and context.bundles:
            message += "\n\nRelevant Precedents:\n"
            for bundle in context.bundles[:3]:
                case = bundle.get("case", {})
                message += f"- {case.get('caption', 'Unknown')}: {case.get('court', 'Unknown Court')}\n"
        
        return message
    
    def _extract_thinking(self, content: str) -> str:
        """Extract thinking process from agent response"""
        # Look for thinking markers in the response
        if "Reasoning:" in content:
            parts = content.split("Reasoning:", 1)
            if len(parts) > 1:
                thinking_part = parts[1].split("\n\n", 1)[0]
                return thinking_part.strip()
        return ""


class ProsecutorAgent(LegalAgent):
    """Prosecutor agent for legal debates"""
    
    def __init__(self, model: str = "gpt-4o-mini"):
        instructions = """You are an experienced prosecutor presenting arguments in court.

Your role is to:
1. Present strong arguments for the prosecution
2. Challenge the defense's claims with evidence and precedent  
3. Cite relevant cases that support prosecution
4. Maintain aggressive but professional demeanor
5. Focus on establishing guilt/liability beyond reasonable doubt

When responding, structure your argument with:
- Main claim
- Supporting evidence
- Legal precedents
- Counter to anticipated defense arguments

Style: Assertive, fact-based, methodical. Use phrases like "The evidence clearly shows...", 
"The defendant's actions demonstrate...", "Precedent in [case] establishes..."."""
        
        super().__init__(
            name="Lead Prosecutor",
            role="prosecutor",
            instructions=instructions,
            model=model
        )


class DefenderAgent(LegalAgent):
    """Defense attorney agent for legal debates"""
    
    def __init__(self, model: str = "gpt-4o-mini"):
        instructions = """You are an experienced defense attorney protecting your client's interests.

Your role is to:
1. Build strong defense arguments
2. Identify prosecution weaknesses and procedural issues
3. Present alternative interpretations of evidence
4. Advocate for client's rights and interests
5. Challenge prosecution assumptions and create reasonable doubt

When responding, structure your defense with:
- Defense position
- Counter-evidence or alternative explanations
- Legal protections and rights
- Challenges to prosecution claims

Style: Protective, strategic, emphatic. Use phrases like "The prosecution fails to prove...", 
"My client's rights were violated when...", "The precedent in [case] protects..."."""
        
        super().__init__(
            name="Defense Attorney",
            role="defender",
            instructions=instructions,
            model=model
        )


class FeedbackAgent(LegalAgent):
    """Legal analyst agent providing feedback on arguments"""
    
    def __init__(self, model: str = "gpt-4o-mini"):
        instructions = """You are an impartial legal analyst and former judge providing expert feedback on legal arguments.

Your role is to:
1. Evaluate argument strength and weaknesses
2. Identify logical fallacies or gaps
3. Suggest improvements and refinements
4. Assess legal precedent relevance
5. Provide balanced, constructive criticism

Structure your feedback as:
- Strengths of each side's arguments
- Weaknesses and vulnerabilities
- Specific improvement recommendations  
- Missing elements or considerations
- Predicted outcome based on arguments presented
- Overall debate quality score (1-10)

Be objective, thorough, and constructive in your analysis."""
        
        super().__init__(
            name="Legal Analyst",
            role="feedback",
            instructions=instructions,
            model=model
        )


class LegalAgentOrchestrator:
    """
    Orchestrates legal agents using LLM-driven coordination
    This implements the Orchestration via LLM pattern from OpenAI Agents SDK
    """
    
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Initialize agents
        self.agents = {
            "prosecutor": ProsecutorAgent(model=model),
            "defender": DefenderAgent(model=model),
            "feedback": FeedbackAgent(model=model)
        }
        
        # Orchestration instructions for the LLM
        self.orchestration_prompt = """You are an orchestrator managing a legal debate between agents.

Your role is to:
1. Determine which agent should speak next based on the debate flow
2. Decide when to transition between prosecution and defense
3. Identify when feedback is needed
4. Manage turn-taking and ensure balanced participation

Current agents available:
- prosecutor: Makes prosecution arguments
- defender: Makes defense arguments  
- feedback: Provides analysis and feedback

Based on the conversation history, determine the next agent to activate.
Respond with a JSON object: {"next_agent": "agent_name", "reason": "explanation"}"""
    
    async def orchestrate_next_agent(self, context: LegalContext) -> str:
        """
        Use LLM to determine which agent should act next
        
        Args:
            context: Current legal context
            
        Returns:
            Name of the next agent to activate
        """
        try:
            # Build conversation summary for orchestration decision
            summary = self._build_conversation_summary(context)
            
            messages = [
                {"role": "system", "content": self.orchestration_prompt},
                {"role": "user", "content": summary}
            ]
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            decision = json.loads(response.choices[0].message.content)
            logger.info(f"Orchestration decision: {decision}")
            
            return decision.get("next_agent", "prosecutor")
            
        except Exception as e:
            logger.error(f"Error in orchestration: {e}")
            # Fallback to simple alternation
            return self._fallback_agent_selection(context)
    
    def _build_conversation_summary(self, context: LegalContext) -> str:
        """Build a summary of the conversation for orchestration"""
        summary = f"""Legal Issue: {context.issue_text}
Case ID: {context.case_id}
Current Turn: {context.current_turn}/{context.max_turns}

Conversation History:
"""
        
        for msg in context.messages[-5:]:  # Last 5 messages
            summary += f"\n{msg.get('role', 'unknown')}: {msg.get('content', '')[:200]}..."
        
        if context.current_turn >= context.max_turns:
            summary += "\n\nDebate has reached maximum turns. Consider providing feedback."
        elif not context.messages:
            summary += "\n\nDebate is just starting. Prosecution should present opening argument."
        
        return summary
    
    def _fallback_agent_selection(self, context: LegalContext) -> str:
        """Fallback agent selection logic"""
        if context.current_turn >= context.max_turns:
            return "feedback"
        
        # Count messages by role
        prosecutor_count = sum(1 for m in context.messages if m.get("role") == "prosecutor")
        defender_count = sum(1 for m in context.messages if m.get("role") == "defender")
        
        # Alternate between prosecutor and defender
        if prosecutor_count <= defender_count:
            return "prosecutor"
        else:
            return "defender"
    
    async def run_agent_turn(self, agent_name: str, context: LegalContext) -> Dict[str, Any]:
        """
        Run a single agent turn
        
        Args:
            agent_name: Name of the agent to run
            context: Current legal context
            
        Returns:
            Agent response
        """
        agent = self.agents.get(agent_name)
        if not agent:
            raise ValueError(f"Unknown agent: {agent_name}")
        
        # Prepare messages for the agent
        messages = []
        
        # Add the issue as the first user message if this is the first turn
        if not context.messages:
            messages.append({
                "role": "user",
                "content": f"Legal Issue: {context.issue_text}\nCase ID: {context.case_id}\n\nPresent your opening argument."
            })
        else:
            # Add recent conversation history
            for msg in context.messages[-3:]:
                role = "assistant" if msg.get("role") in ["prosecutor", "defender", "feedback"] else "user"
                messages.append({
                    "role": role,
                    "content": msg.get("content", "")
                })
            
            # Add instruction for response
            if agent_name == "feedback":
                messages.append({
                    "role": "user",
                    "content": "Analyze the debate so far and provide comprehensive feedback."
                })
            else:
                messages.append({
                    "role": "user",
                    "content": f"Provide your {agent_name} response to the arguments presented."
                })
        
        # Run the agent
        response = await agent.run(messages, context)
        
        # Add response to context
        context.messages.append(response)
        
        return response
    
    async def orchestrate_debate(self, context: LegalContext) -> AsyncIterator[Dict[str, Any]]:
        """
        Orchestrate a complete debate using LLM-driven coordination
        
        Args:
            context: Legal context for the debate
            
        Yields:
            Agent responses as they are generated
        """
        while context.current_turn < context.max_turns:
            # Use LLM to determine next agent
            next_agent = await self.orchestrate_next_agent(context)
            
            # Run the selected agent
            response = await self.run_agent_turn(next_agent, context)
            
            # Update turn counter
            if next_agent in ["prosecutor", "defender"]:
                context.current_turn += 1
            
            yield response
            
            # Small delay for realism
            await asyncio.sleep(0.5)
        
        # Final feedback if not already provided
        if not any(msg.get("role") == "feedback" for msg in context.messages):
            feedback_response = await self.run_agent_turn("feedback", context)
            yield feedback_response
    
    async def analyze_single_argument(
        self, 
        argument: str, 
        role: str = "prosecutor",
        context: Optional[LegalContext] = None
    ) -> Dict[str, Any]:
        """
        Analyze a single legal argument
        
        Args:
            argument: The legal argument to analyze
            role: Role of the lawyer (prosecutor/defender)
            context: Optional legal context
        
        Returns:
            Analysis results with feedback
        """
        if not context:
            context = LegalContext(
                case_id="single-analysis",
                issue_text=argument,
                max_turns=1
            )
        
        # Get the appropriate agent
        agent = self.agents.get(role, self.agents["prosecutor"])
        
        # Analyze the argument
        messages = [{
            "role": "user",
            "content": f"Analyze and improve this legal argument:\n\n{argument}"
        }]
        
        analysis = await agent.run(messages, context)
        
        # Get feedback
        feedback_messages = [{
            "role": "user",
            "content": f"Provide feedback on this {role} argument:\n\n{analysis['content']}"
        }]
        
        feedback = await self.agents["feedback"].run(feedback_messages, context)
        
        return {
            "original_argument": argument,
            "improved_argument": analysis,
            "feedback": feedback,
            "timestamp": datetime.utcnow().isoformat()
        }