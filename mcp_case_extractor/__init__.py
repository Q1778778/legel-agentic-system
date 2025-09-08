"""
MCP Case Extractor - Legal Case Information Extraction System

A comprehensive MCP server for extracting structured case information
from legal documents and conversational interfaces.
"""

__version__ = "1.0.0"
__author__ = "Legal Tech Team"

from .models import (
    ExtractedCaseInfo,
    ExtractionSession,
    ChatboxState,
    Party,
    PartyType,
    CourtInfo,
    LegalIssue,
    ReliefSought,
    DocumentReference,
    CaseType,
    CaseStage,
    DocumentType
)

from .chatbox_agent import ChatboxAgent
from .file_parser import FileParser
from .validators import CaseInfoValidator, ValidationError
from .patterns import LegalPatterns
from .integrations import (
    InfoFetcherIntegration,
    GraphRAGIntegration,
    IntegrationManager
)
from .server import CaseExtractorServer

__all__ = [
    # Models
    "ExtractedCaseInfo",
    "ExtractionSession",
    "ChatboxState",
    "Party",
    "PartyType",
    "CourtInfo",
    "LegalIssue",
    "ReliefSought",
    "DocumentReference",
    "CaseType",
    "CaseStage",
    "DocumentType",
    
    # Core components
    "ChatboxAgent",
    "FileParser",
    "CaseInfoValidator",
    "ValidationError",
    "LegalPatterns",
    
    # Integrations
    "InfoFetcherIntegration",
    "GraphRAGIntegration",
    "IntegrationManager",
    
    # Server
    "CaseExtractorServer",
]