"""
Debate Orchestrator using OpenAI Agents SDK with Orchestration via LLM
"""
from typing import Dict, Any, List, Optional, AsyncIterator
from enum import Enum
import asyncio
import logging
from datetime import datetime

from .legal_agents import LegalAgentOrchestrator, LegalContext
from .graphrag_retrieval import GraphRAGRetrieval
from ..models.schemas import RetrievalRequest

logger = logging.getLogger(__name__)


class DebateMode(str, Enum):
    """Debate mode enumeration"""
    SINGLE = "single"  # Single lawyer analysis
    DEBATE = "debate"  # Multi-agent debate


class DebateState(str, Enum):
    """State of the debate"""
    INITIALIZING = "initializing"
    RETRIEVING = "retrieving"
    DEBATING = "debating"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    ERROR = "error"


class DebateOrchestrator:
    """
    Orchestrates legal debates using OpenAI Agents SDK with LLM-driven coordination
    """
    
    def __init__(
        self,
        mode: DebateMode = DebateMode.DEBATE,
        max_turns: int = 3,
        model: str = "gpt-4o-mini"
    ):
        """
        Initialize the debate orchestrator
        
        Args:
            mode: Debate mode (single or debate)
            max_turns: Maximum debate turns
            model: OpenAI model to use for agents
        """
        self.mode = mode
        self.max_turns = max_turns
        self.model = model
        
        # Initialize the agent orchestrator
        self.agent_orchestrator = LegalAgentOrchestrator(model=model)
        
        # GraphRAG retrieval service
        self.retrieval_service = GraphRAGRetrieval()
        
        # Current state
        self.state = DebateState.INITIALIZING
        self.context: Optional[LegalContext] = None
        
    async def start_debate(
        self,
        case_id: str,
        issue_text: str,
        lawyer_id: Optional[str] = None,
        jurisdiction: Optional[str] = None
    ) -> LegalContext:
        """
        Start a new debate
        
        Args:
            case_id: Case identifier
            issue_text: Legal issue description
            lawyer_id: Optional lawyer ID for retrieval
            jurisdiction: Optional jurisdiction filter
            
        Returns:
            Initialized debate context
        """
        logger.info(f"Starting debate for case {case_id} in {self.mode} mode")
        
        # Set state
        self.state = DebateState.RETRIEVING
        
        # Retrieve relevant past cases
        retrieval_request = RetrievalRequest(
            issue_text=issue_text,
            lawyer_id=lawyer_id,
            jurisdiction=jurisdiction,
            limit=5
        )
        
        try:
            retrieval_response = await self.retrieval_service.retrieve_past_defenses(
                retrieval_request
            )
            
            # Convert bundles to dict for context
            bundles_dict = [
                bundle.model_dump() for bundle in retrieval_response.bundles
            ]
            
        except Exception as e:
            logger.error(f"Error retrieving past cases: {e}")
            bundles_dict = []
        
        # Initialize context
        self.context = LegalContext(
            case_id=case_id,
            issue_text=issue_text,
            bundles=bundles_dict,
            max_turns=self.max_turns,
            metadata={
                "mode": self.mode.value,
                "started_at": datetime.utcnow().isoformat(),
                "model": self.model,
                "bundles_retrieved": len(bundles_dict)
            }
        )
        
        self.state = DebateState.DEBATING
        
        return self.context
    
    async def execute_single_turn(self) -> Optional[Dict[str, Any]]:
        """
        Execute a single turn of the debate
        
        Returns:
            Agent response for this turn
        """
        if not self.context:
            raise ValueError("Debate not started. Call start_debate first.")
        
        if self.context.current_turn >= self.context.max_turns:
            self.state = DebateState.COMPLETED
            return None
        
        try:
            if self.mode == DebateMode.SINGLE:
                # Single lawyer analysis mode
                response = await self.agent_orchestrator.analyze_single_argument(
                    argument=self.context.issue_text,
                    role="prosecutor",  # Default to prosecutor for single analysis
                    context=self.context
                )
                self.context.current_turn = self.context.max_turns  # Mark as complete
                self.state = DebateState.COMPLETED
                return response
            else:
                # Debate mode - use orchestration to determine next agent
                next_agent = await self.agent_orchestrator.orchestrate_next_agent(self.context)
                response = await self.agent_orchestrator.run_agent_turn(next_agent, self.context)
                
                # Update turn counter based on agent type
                if next_agent in ["prosecutor", "defender"]:
                    self.context.current_turn += 1
                
                # Check if debate is complete
                if self.context.current_turn >= self.context.max_turns:
                    self.state = DebateState.ANALYZING
                    
                    # Add feedback if not already present
                    if not any(msg.get("role") == "feedback" for msg in self.context.messages):
                        feedback = await self.agent_orchestrator.run_agent_turn("feedback", self.context)
                        self.state = DebateState.COMPLETED
                        return feedback
                    
                    self.state = DebateState.COMPLETED
                
                return response
                
        except Exception as e:
            logger.error(f"Error executing turn: {e}")
            self.state = DebateState.ERROR
            raise
    
    async def run_complete_debate(self) -> LegalContext:
        """
        Run a complete debate until max turns reached
        
        Returns:
            Final debate context with all messages
        """
        if not self.context:
            raise ValueError("Debate not started. Call start_debate first.")
        
        if self.mode == DebateMode.SINGLE:
            # Single analysis mode
            await self.execute_single_turn()
        else:
            # Full debate mode
            async for _ in self.agent_orchestrator.orchestrate_debate(self.context):
                pass  # Just run through all turns
        
        self.state = DebateState.COMPLETED
        return self.context
    
    async def stream_debate(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream debate messages as they are generated
        
        Yields:
            Agent messages as they are created
        """
        if not self.context:
            raise ValueError("Debate not started. Call start_debate first.")
        
        if self.mode == DebateMode.SINGLE:
            # Single analysis mode
            result = await self.execute_single_turn()
            if result:
                yield result
        else:
            # Stream debate messages
            async for message in self.agent_orchestrator.orchestrate_debate(self.context):
                yield message
        
        self.state = DebateState.COMPLETED
    
    def get_debate_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the debate
        
        Returns:
            Dictionary containing debate summary
        """
        if not self.context:
            return {"error": "No debate context"}
        
        # Count messages by role
        role_counts = {}
        for msg in self.context.messages:
            role = msg.get("role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1
        
        # Extract winner from feedback if present
        predicted_winner = "undecided"
        feedback_messages = [m for m in self.context.messages if m.get("role") == "feedback"]
        if feedback_messages:
            feedback_content = feedback_messages[-1].get("content", "").lower()
            if "prosecution" in feedback_content and ("stronger" in feedback_content or "prevail" in feedback_content):
                predicted_winner = "prosecution"
            elif "defense" in feedback_content and ("stronger" in feedback_content or "prevail" in feedback_content):
                predicted_winner = "defense"
        
        summary = {
            "case_id": self.context.case_id,
            "issue": self.context.issue_text,
            "mode": self.mode.value,
            "state": self.state.value,
            "total_turns": self.context.current_turn,
            "max_turns": self.context.max_turns,
            "total_messages": len(self.context.messages),
            "messages_by_role": role_counts,
            "bundles_used": len(self.context.bundles),
            "metadata": self.context.metadata
        }
        
        # Add winner for debate mode
        if self.mode == DebateMode.DEBATE:
            summary["predicted_winner"] = predicted_winner
        
        # Add timestamps
        if self.context.messages:
            summary["started_at"] = self.context.messages[0].get("timestamp")
            summary["ended_at"] = self.context.messages[-1].get("timestamp")
        
        return summary
    
    def get_messages(self) -> List[Dict[str, Any]]:
        """
        Get all messages from the debate
        
        Returns:
            List of all messages
        """
        if not self.context:
            return []
        return self.context.messages
    
    def reset(self):
        """Reset the orchestrator for a new debate"""
        self.state = DebateState.INITIALIZING
        self.context = None