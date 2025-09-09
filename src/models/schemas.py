"""Pydantic schemas for data validation and serialization."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum


class StageType(str, Enum):
    """Legal proceeding stages."""
    MOTION_TO_DISMISS = "motion_to_dismiss"
    MOTION_TO_SUPPRESS = "motion_to_suppress"
    SUMMARY_JUDGMENT = "summary_judgment"
    TRIAL = "trial"
    APPEAL = "appeal"
    ORAL_ARGUMENT = "oral_argument"
    SENTENCING = "sentencing"


class DispositionType(str, Enum):
    """Case disposition types."""
    GRANTED = "granted"
    DENIED = "denied"
    PARTIAL = "partial"
    DISMISSED = "dismissed"
    SETTLED = "settled"
    PENDING = "pending"


class RoleType(str, Enum):
    """Argument segment roles."""
    OPENING = "opening"
    REBUTTAL = "rebuttal"
    CLOSING = "closing"
    RESPONSE = "response"
    QUESTION = "question"
    ANSWER = "answer"


class Lawyer(BaseModel):
    """Lawyer information."""
    id: str
    name: str
    bar_id: Optional[str] = None
    firm: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "l_555",
                "name": "John Roe",
                "bar_id": "1234",
                "firm": "Roe & Associates"
            }
        }


class Judge(BaseModel):
    """Judge information."""
    id: str
    name: str
    court: Optional[str] = None
    appointed_date: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "j_999",
                "name": "Hon. Jane Smith",
                "court": "Supreme Court"
            }
        }


class Issue(BaseModel):
    """Legal issue taxonomy."""
    id: str
    title: str
    taxonomy_path: List[str] = Field(default_factory=list)
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "i_42",
                "title": "Fourth Amendment - Search & Seizure",
                "taxonomy_path": ["Constitutional", "Fourth Amendment", "Search & Seizure"]
            }
        }


class Citation(BaseModel):
    """Legal citation."""
    text: str
    normalized: Optional[str] = None
    type: Optional[str] = None  # case, statute, regulation
    
    class Config:
        json_schema_extra = {
            "example": {
                "text": "392 U.S. 1 (1968)",
                "normalized": "Terry v. Ohio, 392 U.S. 1 (1968)",
                "type": "case"
            }
        }


class Case(BaseModel):
    """Case information."""
    id: str
    caption: Optional[str] = None
    court: Optional[str] = None
    jurisdiction: Optional[str] = None
    judge_id: Optional[str] = None
    judge_name: Optional[str] = None
    filed_date: Optional[datetime] = None
    outcome: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "case_123",
                "caption": "State v. Doe",
                "court": "Supreme Court",
                "jurisdiction": "NY",
                "judge_name": "Hon. Jane Smith",
                "filed_date": "2020-05-12T00:00:00"
            }
        }


class ArgumentSegment(BaseModel):
    """Segment of legal argument."""
    segment_id: str
    argument_id: str
    text: str
    role: RoleType
    seq: int = Field(ge=0)
    citations: List[str] = Field(default_factory=list)
    score: Optional[float] = Field(None, ge=0, le=1)
    embedding: Optional[List[float]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "segment_id": "s_1",
                "argument_id": "arg_111",
                "text": "The search violated established precedent...",
                "role": "opening",
                "seq": 1,
                "citations": ["392 U.S. 1 (1968)"],
                "score": 0.85
            }
        }


class GraphExplanation(BaseModel):
    """Explanation of graph-based scoring."""
    graph_hops: List[str] = Field(default_factory=list)
    boosts: Dict[str, float] = Field(default_factory=dict)
    final_score: float
    
    class Config:
        json_schema_extra = {
            "example": {
                "graph_hops": ["Issue→Argument", "Argument→Case"],
                "boosts": {"judge_match": 0.1, "citation_overlap": 0.15},
                "final_score": 1.37
            }
        }


class ConfidenceScore(BaseModel):
    """Confidence scoring."""
    value: float = Field(ge=0, le=1)
    explanation: Optional[GraphExplanation] = None
    features: Dict[str, Any] = Field(default_factory=dict)
    
    @validator("value")
    def round_value(cls, v):
        """Round confidence to 2 decimal places."""
        return round(v, 2)


class ArgumentBundle(BaseModel):
    """Complete argument bundle with metadata."""
    argument_id: str
    confidence: ConfidenceScore
    case: Case
    lawyer: Optional[Lawyer] = None
    issue: Issue
    stage: Optional[StageType] = None
    disposition: Optional[DispositionType] = None
    citations: List[Citation] = Field(default_factory=list)
    segments: List[ArgumentSegment] = Field(default_factory=list)
    explanation: Optional[GraphExplanation] = None
    signature_hash: Optional[str] = None
    tenant: str = "default"
    
    class Config:
        json_schema_extra = {
            "example": {
                "argument_id": "ARG123",
                "confidence": {"value": 0.82},
                "case": {"id": "case_123", "caption": "State v. Doe"},
                "issue": {"id": "i_42", "title": "Fourth Amendment"},
                "segments": []
            }
        }


class RetrievalRequest(BaseModel):
    """Request for past defense retrieval."""
    lawyer_id: Optional[str] = None
    current_issue_id: Optional[str] = None
    issue_text: Optional[str] = None
    jurisdiction: Optional[str] = None
    judge_id: Optional[str] = None
    since: Optional[datetime] = None
    stage: Optional[StageType] = None
    tenant: str = "default"
    limit: int = Field(default=10, ge=1, le=100)
    
    @validator("issue_text", always=True)
    def at_least_one_required(cls, v, values):
        """Ensure at least one search parameter is provided."""
        # Check if at least one of the three fields is provided
        if not v and not values.get("lawyer_id") and not values.get("current_issue_id"):
            raise ValueError("At least one of lawyer_id, current_issue_id, or issue_text is required")
        return v


class RetrievalResponse(BaseModel):
    """Response from retrieval system."""
    bundles: List[ArgumentBundle]
    total_count: int
    query_time_ms: int
    confidence_threshold: float = 0.5
    metrics: Optional[Dict[str, Any]] = None  # Core metrics if requested
    
    class Config:
        json_schema_extra = {
            "example": {
                "bundles": [],
                "total_count": 5,
                "query_time_ms": 1250,
                "confidence_threshold": 0.5
            }
        }


class AnalysisRequest(BaseModel):
    """Request for legal analysis."""
    bundles: List[ArgumentBundle]
    context: Optional[str] = None
    include_prosecution: bool = True
    include_judge: bool = True
    max_length: int = Field(default=2000, ge=100, le=10000)
    tenant: str = "default"


class AnalysisArtifact(BaseModel):
    """Single analysis output."""
    text: str
    confidence: float = Field(ge=0, le=1)
    role: str
    citations_used: List[str] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    """Response from analysis system."""
    defense: AnalysisArtifact
    prosecution: Optional[AnalysisArtifact] = None
    judge: Optional[AnalysisArtifact] = None
    script: Optional[AnalysisArtifact] = None
    overall_confidence: float = Field(ge=0, le=1)
    generation_time_ms: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "defense": {
                    "text": "Your Honor, the search clearly violated...",
                    "confidence": 0.85,
                    "role": "defense",
                    "citations_used": ["392 U.S. 1"]
                },
                "overall_confidence": 0.82,
                "generation_time_ms": 3500
            }
        }


# Case Management Models

class CaseStatusType(str, Enum):
    """Case status types."""
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class CaseParty(BaseModel):
    """Party in a legal case."""
    name: str
    role: str  # plaintiff, defendant, witness, etc.
    contact_info: Optional[str] = None
    represented_by: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "role": "plaintiff",
                "contact_info": "john.doe@email.com",
                "represented_by": "Smith & Associates"
            }
        }


class CaseCourtInfo(BaseModel):
    """Court information for a case."""
    name: str
    jurisdiction: str
    judge_name: Optional[str] = None
    case_number: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Superior Court of California",
                "jurisdiction": "California",
                "judge_name": "Hon. Jane Smith",
                "case_number": "CV-2024-001234"
            }
        }


class CaseDocument(BaseModel):
    """Document attached to a case."""
    id: str
    filename: str
    file_type: str
    upload_date: datetime
    extracted_data: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "doc_123",
                "filename": "contract.pdf",
                "file_type": "pdf",
                "upload_date": "2024-01-20T10:00:00Z",
                "extracted_data": {"key_terms": ["delivery", "payment"]}
            }
        }


class CaseTimeline(BaseModel):
    """Timeline entry for a case."""
    id: str
    date: datetime
    event_type: str
    description: str
    created_by: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "timeline_123",
                "date": "2024-01-20T10:00:00Z",
                "event_type": "case_created",
                "description": "Case created via chat extraction",
                "created_by": "user_123"
            }
        }


class CaseCreate(BaseModel):
    """Request model for creating a new case."""
    title: str
    description: Optional[str] = None
    parties: List[CaseParty] = Field(default_factory=list)
    court_info: Optional[CaseCourtInfo] = None
    issues: List[str] = Field(default_factory=list)
    extraction_method: Optional[str] = None  # "chat" or "file"
    extraction_session_id: Optional[str] = None
    created_by: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "Contract Dispute - ABC Corp vs XYZ Inc",
                "description": "Breach of contract claim involving late delivery",
                "parties": [
                    {
                        "name": "ABC Corp",
                        "role": "plaintiff",
                        "represented_by": "Johnson & Associates"
                    }
                ],
                "court_info": {
                    "name": "Superior Court",
                    "jurisdiction": "California"
                },
                "issues": ["contract_breach", "damages"],
                "extraction_method": "chat"
            }
        }


class CaseUpdate(BaseModel):
    """Request model for updating a case."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CaseStatusType] = None
    parties: Optional[List[CaseParty]] = None
    court_info: Optional[CaseCourtInfo] = None
    issues: Optional[List[str]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "Updated Contract Dispute Title",
                "status": "active",
                "issues": ["contract_breach", "damages", "attorney_fees"]
            }
        }


class CaseResponse(BaseModel):
    """Response model for case operations."""
    id: str
    title: str
    description: Optional[str] = None
    status: CaseStatusType = CaseStatusType.DRAFT
    parties: List[CaseParty] = Field(default_factory=list)
    court_info: Optional[CaseCourtInfo] = None
    issues: List[str] = Field(default_factory=list)
    documents: List[CaseDocument] = Field(default_factory=list)
    timeline: List[CaseTimeline] = Field(default_factory=list)
    extraction_method: Optional[str] = None
    extraction_session_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "case_123",
                "title": "Contract Dispute - ABC Corp vs XYZ Inc",
                "description": "Breach of contract claim",
                "status": "active",
                "parties": [],
                "issues": ["contract_breach"],
                "documents": [],
                "timeline": [],
                "created_at": "2024-01-20T10:00:00Z",
                "updated_at": "2024-01-20T10:00:00Z"
            }
        }


class CaseListResponse(BaseModel):
    """Response model for listing cases."""
    cases: List[CaseResponse]
    total_count: int
    skip: int
    limit: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "cases": [],
                "total_count": 10,
                "skip": 0,
                "limit": 20
            }
        }