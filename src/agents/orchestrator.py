"""Debate orchestrator using OpenAI Swarm pattern for multi-agent coordination."""

from typing import Dict, Any, List, Optional, AsyncIterator
from enum import Enum
import asyncio
import structlog
from datetime import datetime

from .base_agent import AgentContext, AgentMessage
from .lawyer_agents import ProsecutorAgent, DefenderAgent, FeedbackAgent, LawyerAgent
from .config_validator import ConfigValidator
from ..services.graphrag_retrieval import GraphRAGRetrieval
from ..models.schemas import RetrievalRequest

logger = structlog.get_logger()


class DebateMode(str, Enum):
    """Debate mode enumeration."""
    SINGLE = "single"  # Single lawyer analysis
    DEBATE = "debate"  # Multi-agent debate
    FEEDBACK = "feedback"  # With feedback agent


class DebateState(str, Enum):
    """State of the debate."""
    INITIALIZING = "initializing"
    RETRIEVING = "retrieving"
    DEBATING = "debating"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    ERROR = "error"


class DebateOrchestrator:
    """Orchestrates legal debates using Swarm pattern."""
    
    def __init__(
        self,
        mode: DebateMode = DebateMode.DEBATE,
        max_turns: int = 3,
        enable_feedback: bool = True,
        api_key: Optional[str] = None
    ):
        """Initialize the debate orchestrator.
        
        Args:
            mode: Debate mode (single or debate)
            max_turns: Maximum debate turns
            enable_feedback: Whether to use feedback agent
            api_key: OpenAI API key
        """
        self.mode = mode
        self.max_turns = max_turns
        self.enable_feedback = enable_feedback
        self.api_key = api_key
        
        # Initialize agents based on mode
        self.agents = self._initialize_agents()
        
        # GraphRAG retrieval service
        self.retrieval_service = GraphRAGRetrieval()
        
        # Current state
        self.state = DebateState.INITIALIZING
        self.context: Optional[AgentContext] = None
        
    def _initialize_agents(self) -> Dict[str, Any]:
        """Initialize agents based on mode.
        
        Returns:
            Dictionary of initialized agents
        """
        agents = {}
        
        # Validate environment
        env_status = ConfigValidator.validate_environment()
        
        if self.mode == DebateMode.SINGLE:
            config = ConfigValidator.get_agent_config("lawyer")
            agents["lawyer"] = LawyerAgent(
                name=config["name"],
                role=config["role"],
                api_key=config["api_key"],
                temperature=config["temperature"],
                max_tokens=config["max_tokens"],
                enable_mock=config["enable_mock"]
            )
        else:
            # Initialize prosecutor
            prosecutor_config = ConfigValidator.get_agent_config("prosecutor")
            agents["prosecutor"] = ProsecutorAgent(
                name=prosecutor_config["name"],
                role=prosecutor_config["role"],
                api_key=prosecutor_config["api_key"],
                temperature=prosecutor_config["temperature"],
                max_tokens=prosecutor_config["max_tokens"],
                enable_mock=prosecutor_config["enable_mock"]
            )
            
            # Initialize defender
            defender_config = ConfigValidator.get_agent_config("defender")
            agents["defender"] = DefenderAgent(
                name=defender_config["name"],
                role=defender_config["role"],
                api_key=defender_config["api_key"],
                temperature=defender_config["temperature"],
                max_tokens=defender_config["max_tokens"],
                enable_mock=defender_config["enable_mock"]
            )
        
        if self.enable_feedback:
            feedback_config = ConfigValidator.get_agent_config("feedback")
            agents["feedback"] = FeedbackAgent(
                name=feedback_config["name"],
                role=feedback_config["role"],
                api_key=feedback_config["api_key"],
                temperature=feedback_config["temperature"],
                max_tokens=feedback_config["max_tokens"],
                enable_mock=feedback_config["enable_mock"]
            )
        
        # Log initialization status
        if not env_status["openai_api_key"]:
            logger.warning("Agents initialized in mock mode - no OpenAI API key")
        else:
            logger.info(f"Agents initialized with OpenAI API for {self.mode} mode")
        
        return agents
    
    async def start_debate(
        self,
        case_id: str,
        issue_text: str,
        lawyer_id: Optional[str] = None,
        jurisdiction: Optional[str] = None
    ) -> AgentContext:
        """Start a new debate.
        
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
        
        retrieval_response = await self.retrieval_service.retrieve_past_defenses(
            retrieval_request
        )
        
        # Convert bundles to dict for context
        bundles_dict = [
            bundle.model_dump() for bundle in retrieval_response.bundles
        ]
        
        # Initialize context
        self.context = AgentContext(
            case_id=case_id,
            issue_text=issue_text,
            bundles=bundles_dict,
            max_turns=self.max_turns,
            metadata={
                "mode": self.mode,
                "started_at": datetime.utcnow().isoformat(),
                "retrieval_time_ms": retrieval_response.query_time_ms,
                "bundles_retrieved": len(bundles_dict)
            }
        )
        
        self.state = DebateState.DEBATING
        
        return self.context
    
    async def execute_turn(self) -> List[AgentMessage]:
        """Execute a single turn of the debate.
        
        Returns:
            List of messages generated in this turn
        """
        if not self.context:
            raise ValueError("Debate not started. Call start_debate first.")
        
        if self.context.current_turn >= self.context.max_turns:
            self.state = DebateState.COMPLETED
            return []
        
        turn_messages = []
        
        try:
            if self.mode == DebateMode.SINGLE:
                # Single lawyer analysis
                message = await self.agents["lawyer"].process(self.context)
                self.context.add_message(message)
                turn_messages.append(message)
                
            else:
                # Debate mode - alternate between prosecutor and defender
                
                # Prosecutor's turn
                prosecutor_msg = await self.agents["prosecutor"].process(self.context)
                self.context.add_message(prosecutor_msg)
                turn_messages.append(prosecutor_msg)
                
                # Small delay for realism
                await asyncio.sleep(0.5)
                
                # Defender's turn
                defender_msg = await self.agents["defender"].process(self.context)
                self.context.add_message(defender_msg)
                turn_messages.append(defender_msg)
            
            # Increment turn counter
            self.context.current_turn += 1
            
            # Check if debate is complete
            if self.context.current_turn >= self.context.max_turns:
                self.state = DebateState.ANALYZING
                
                # Add feedback if enabled
                if self.enable_feedback and "feedback" in self.agents:
                    feedback_msg = await self.agents["feedback"].process(self.context)
                    self.context.add_message(feedback_msg)
                    turn_messages.append(feedback_msg)
                
                self.state = DebateState.COMPLETED
            
            return turn_messages
            
        except Exception as e:
            logger.error(f"Error executing turn: {e}")
            self.state = DebateState.ERROR
            raise
    
    async def run_complete_debate(self) -> AgentContext:
        """Run a complete debate until max turns reached.
        
        Returns:
            Final debate context with all messages
        """
        if not self.context:
            raise ValueError("Debate not started. Call start_debate first.")
        
        while self.state == DebateState.DEBATING:
            await self.execute_turn()
        
        return self.context
    
    async def stream_debate(self) -> AsyncIterator[AgentMessage]:
        """Stream debate messages as they are generated.
        
        Yields:
            Agent messages as they are created
        """
        if not self.context:
            raise ValueError("Debate not started. Call start_debate first.")
        
        while self.state == DebateState.DEBATING:
            messages = await self.execute_turn()
            for message in messages:
                yield message
        
        # Yield final feedback if it was generated
        if self.state == DebateState.COMPLETED and self.enable_feedback:
            feedback_messages = self.context.get_messages_by_role("feedback")
            if feedback_messages:
                yield feedback_messages[-1]
    
    def get_debate_summary(self) -> Dict[str, Any]:
        """Get a summary of the debate.
        
        Returns:
            Dictionary containing debate summary
        """
        if not self.context:
            return {"error": "No debate context"}
        
        prosecution_msgs = self.context.get_messages_by_role("prosecutor")
        defense_msgs = self.context.get_messages_by_role("defender")
        feedback_msgs = self.context.get_messages_by_role("feedback")
        lawyer_msgs = self.context.get_messages_by_role("lawyer")
        
        # Calculate statistics
        total_citations = sum(len(msg.citations) for msg in self.context.messages)
        avg_confidence = (
            sum(msg.confidence for msg in self.context.messages) / 
            len(self.context.messages)
        ) if self.context.messages else 0
        
        summary = {
            "case_id": self.context.case_id,
            "issue": self.context.issue_text,
            "mode": self.mode,
            "state": self.state,
            "total_turns": self.context.current_turn,
            "total_messages": len(self.context.messages),
            "messages_by_role": {
                "prosecutor": len(prosecution_msgs),
                "defender": len(defense_msgs),
                "feedback": len(feedback_msgs),
                "lawyer": len(lawyer_msgs)
            },
            "total_citations": total_citations,
            "average_confidence": round(avg_confidence, 3),
            "bundles_used": len(self.context.bundles),
            "metadata": self.context.metadata
        }
        
        # Add winner determination for debate mode
        if self.mode == DebateMode.DEBATE and feedback_msgs:
            # Extract winner from feedback (simplified - could use LLM)
            feedback_content = feedback_msgs[-1].content.lower()
            if "prosecution" in feedback_content and "stronger" in feedback_content:
                summary["predicted_winner"] = "prosecution"
            elif "defense" in feedback_content and "stronger" in feedback_content:
                summary["predicted_winner"] = "defense"
            else:
                summary["predicted_winner"] = "undecided"
        
        return summary
    
    def reset(self):
        """Reset the orchestrator for a new debate."""
        self.state = DebateState.INITIALIZING
        self.context = None