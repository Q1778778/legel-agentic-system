"""
Data models for extracted case information.

This module defines the unified data model for legal case information
extracted from various sources (chatbox, documents).
"""

from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class CaseType(str, Enum):
    """Types of legal cases."""
    CIVIL = "civil"
    CRIMINAL = "criminal"
    FAMILY = "family"
    BANKRUPTCY = "bankruptcy"
    ADMINISTRATIVE = "administrative"
    APPEAL = "appeal"
    OTHER = "other"


class CaseStage(str, Enum):
    """Stages of legal proceedings."""
    FILING = "filing"
    DISCOVERY = "discovery"
    MOTION_PRACTICE = "motion_practice"
    TRIAL = "trial"
    POST_TRIAL = "post_trial"
    APPEAL = "appeal"
    ENFORCEMENT = "enforcement"
    CLOSED = "closed"


class PartyType(str, Enum):
    """Types of parties in legal cases."""
    PLAINTIFF = "plaintiff"
    DEFENDANT = "defendant"
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    APPELLANT = "appellant"
    APPELLEE = "appellee"
    INTERVENOR = "intervenor"
    AMICUS = "amicus"
    THIRD_PARTY = "third_party"


class DocumentType(str, Enum):
    """Types of legal documents."""
    COMPLAINT = "complaint"
    ANSWER = "answer"
    MOTION = "motion"
    BRIEF = "brief"
    ORDER = "order"
    JUDGMENT = "judgment"
    NOTICE = "notice"
    DISCOVERY = "discovery"
    PLEADING = "pleading"
    OTHER = "other"


class Party(BaseModel):
    """Represents a party in a legal case."""
    model_config = ConfigDict(extra='allow')
    
    name: str = Field(..., description="Name of the party")
    party_type: PartyType = Field(..., description="Type of party")
    attorneys: Optional[List[str]] = Field(default=None, description="List of attorneys representing the party")
    contact_info: Optional[Dict[str, str]] = Field(default=None, description="Contact information")
    role_description: Optional[str] = Field(default=None, description="Description of party's role in the case")


class CourtInfo(BaseModel):
    """Information about the court handling the case."""
    model_config = ConfigDict(extra='allow')
    
    name: str = Field(..., description="Name of the court")
    jurisdiction: str = Field(..., description="Court jurisdiction (federal, state, etc.)")
    location: Optional[str] = Field(default=None, description="Physical location of the court")
    judge: Optional[str] = Field(default=None, description="Presiding judge")
    department: Optional[str] = Field(default=None, description="Court department or division")


class LegalIssue(BaseModel):
    """Represents a legal issue in the case."""
    model_config = ConfigDict(extra='allow')
    
    issue: str = Field(..., description="Description of the legal issue")
    category: str = Field(..., description="Category of the issue (e.g., contract, tort, criminal)")
    is_primary: bool = Field(default=False, description="Whether this is a primary issue")
    related_claims: Optional[List[str]] = Field(default=None, description="Related legal claims")
    related_defenses: Optional[List[str]] = Field(default=None, description="Related legal defenses")


class ReliefSought(BaseModel):
    """Relief or remedies sought in the case."""
    model_config = ConfigDict(extra='allow')
    
    monetary_damages: Optional[float] = Field(default=None, description="Monetary damages amount")
    injunctive_relief: Optional[str] = Field(default=None, description="Description of injunctive relief")
    declaratory_relief: Optional[str] = Field(default=None, description="Description of declaratory relief")
    other_relief: Optional[List[str]] = Field(default=None, description="Other types of relief sought")


class DocumentReference(BaseModel):
    """Reference to a legal document or authority."""
    model_config = ConfigDict(extra='allow')
    
    reference_type: Literal["case", "statute", "regulation", "rule", "other"] = Field(..., description="Type of reference")
    citation: str = Field(..., description="Citation or reference")
    title: Optional[str] = Field(default=None, description="Title or name of the referenced document")
    relevance: Optional[str] = Field(default=None, description="Relevance to the current case")


class ExtractedCaseInfo(BaseModel):
    """Unified data model for extracted case information."""
    model_config = ConfigDict(extra='allow')
    
    # Basic Information
    case_number: Optional[str] = Field(default=None, description="Official case number")
    case_title: Optional[str] = Field(default=None, description="Full case title")
    filing_date: Optional[datetime] = Field(default=None, description="Date case was filed")
    case_type: Optional[CaseType] = Field(default=None, description="Type of case")
    case_stage: Optional[CaseStage] = Field(default=None, description="Current stage of proceedings")
    
    # Parties
    parties: List[Party] = Field(default_factory=list, description="All parties involved in the case")
    
    # Court Information
    court_info: Optional[CourtInfo] = Field(default=None, description="Court handling the case")
    
    # Legal Issues
    legal_issues: List[LegalIssue] = Field(default_factory=list, description="Legal issues in the case")
    
    # Key Facts
    fact_summary: Optional[str] = Field(default=None, description="Summary of key facts")
    disputed_facts: Optional[List[str]] = Field(default=None, description="List of disputed facts")
    
    # Relief and Damages
    relief_sought: Optional[ReliefSought] = Field(default=None, description="Relief sought by parties")
    
    # Document References
    document_references: List[DocumentReference] = Field(default_factory=list, description="Citations and references")
    
    # Metadata
    extraction_source: Literal["chatbox", "document", "merged"] = Field(..., description="Source of extraction")
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow, description="When extraction occurred")
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence in extraction accuracy")
    document_type: Optional[DocumentType] = Field(default=None, description="Type of source document")
    
    # Additional fields for flexibility
    additional_info: Dict[str, Any] = Field(default_factory=dict, description="Additional extracted information")


class ExtractionSession(BaseModel):
    """Represents an extraction session."""
    model_config = ConfigDict(extra='allow')
    
    session_id: str = Field(..., description="Unique session identifier")
    extraction_type: Literal["chatbox", "document", "batch"] = Field(..., description="Type of extraction")
    status: Literal["active", "paused", "completed", "failed"] = Field(..., description="Session status")
    extracted_info: ExtractedCaseInfo = Field(..., description="Extracted case information")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Session creation time")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update time")
    messages: List[Dict[str, Any]] = Field(default_factory=list, description="Conversation history for chatbox")
    files_processed: List[str] = Field(default_factory=list, description="List of processed files")
    error_messages: List[str] = Field(default_factory=list, description="Any errors encountered")
    
    
class ChatboxState(BaseModel):
    """State management for chatbox conversations."""
    model_config = ConfigDict(extra='allow')
    
    current_field: Optional[str] = Field(default=None, description="Field currently being extracted")
    fields_completed: List[str] = Field(default_factory=list, description="List of completed fields")
    fields_pending: List[str] = Field(default_factory=list, description="List of pending fields")
    question_count: int = Field(default=0, description="Number of questions asked")
    last_question: Optional[str] = Field(default=None, description="Last question asked")
    context: Dict[str, Any] = Field(default_factory=dict, description="Conversation context")