"""OpenAI Agents SDK integration for legal argumentation system."""

from .lawyer_agents import (
    ProsecutorAgent,
    DefenderAgent,
    FeedbackAgent,
    LawyerAgent
)
from .orchestrator import DebateOrchestrator
from .workflow_engine import WorkflowEngine
from .websocket_manager import WebSocketManager, ws_manager

__all__ = [
    "ProsecutorAgent",
    "DefenderAgent",
    "FeedbackAgent",
    "LawyerAgent",
    "DebateOrchestrator",
    "WorkflowEngine",
    "WebSocketManager",
    "ws_manager"
]