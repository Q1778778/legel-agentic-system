"""MCP Lawyer Server - Conversational AI Legal Assistant with Opponent Simulation."""

from .server import MCPLawyerServer
from .lawyer_agent import LawyerAgent
from .opponent_simulator import OpponentSimulator
from .conversation_manager import ConversationManager, ConversationSession
from .legal_context import (
    LegalContext,
    CaseInfo,
    LawyerInfo,
    ArgumentContext,
    ConversationTurn,
    PartyRole
)

__version__ = "1.0.0"
__author__ = "Legal AI Team"

__all__ = [
    "MCPLawyerServer",
    "LawyerAgent",
    "OpponentSimulator",
    "ConversationManager",
    "ConversationSession",
    "LegalContext",
    "CaseInfo",
    "LawyerInfo",
    "ArgumentContext",
    "ConversationTurn",
    "PartyRole"
]