"""OpenAI Agents SDK integration for legal argumentation system."""

from .base_agent import BaseAgent, AgentMessage, AgentContext
from .lawyer_agents import (
    ProsecutorAgent,
    DefenderAgent,
    FeedbackAgent,
    LawyerAgent
)
from .orchestrator import DebateOrchestrator, DebateMode, DebateState
from .workflow_engine import WorkflowEngine
from .websocket_manager import WebSocketManager, ws_manager
from .config_validator import ConfigValidator

__all__ = [
    # Base classes
    "BaseAgent",
    "AgentMessage",
    "AgentContext",
    
    # Specific agents
    "ProsecutorAgent",
    "DefenderAgent",
    "FeedbackAgent",
    "LawyerAgent",
    
    # Orchestration
    "DebateOrchestrator",
    "DebateMode", 
    "DebateState",
    "WorkflowEngine",
    
    # Communication
    "WebSocketManager",
    "ws_manager",
    
    # Configuration
    "ConfigValidator"
]