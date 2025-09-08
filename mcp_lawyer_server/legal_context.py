"""Legal context management for conversation sessions."""

from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json


class PartyRole(str, Enum):
    """Roles of parties in legal proceedings."""
    PLAINTIFF = "plaintiff"
    DEFENDANT = "defendant"
    APPELLANT = "appellant"
    APPELLEE = "appellee"
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"


@dataclass
class LawyerInfo:
    """Information about a lawyer."""
    id: str
    name: str
    firm: Optional[str] = None
    bar_id: Optional[str] = None
    specializations: List[str] = field(default_factory=list)
    years_experience: Optional[int] = None
    win_rate: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "firm": self.firm,
            "bar_id": self.bar_id,
            "specializations": self.specializations,
            "years_experience": self.years_experience,
            "win_rate": self.win_rate
        }


@dataclass
class CaseInfo:
    """Information about the current case."""
    case_id: str
    caption: str
    court: str
    jurisdiction: str
    case_type: str
    filed_date: datetime
    judge_name: Optional[str] = None
    judge_id: Optional[str] = None
    our_role: Optional[PartyRole] = None
    opposing_role: Optional[PartyRole] = None
    key_issues: List[str] = field(default_factory=list)
    current_stage: Optional[str] = None
    upcoming_deadlines: Dict[str, datetime] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "case_id": self.case_id,
            "caption": self.caption,
            "court": self.court,
            "jurisdiction": self.jurisdiction,
            "case_type": self.case_type,
            "filed_date": self.filed_date.isoformat() if self.filed_date else None,
            "judge_name": self.judge_name,
            "judge_id": self.judge_id,
            "our_role": self.our_role.value if self.our_role else None,
            "opposing_role": self.opposing_role.value if self.opposing_role else None,
            "key_issues": self.key_issues,
            "current_stage": self.current_stage,
            "upcoming_deadlines": {
                k: v.isoformat() for k, v in self.upcoming_deadlines.items()
            }
        }


@dataclass
class ArgumentContext:
    """Context for a legal argument."""
    argument_id: str
    text: str
    supporting_precedents: List[str] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)
    confidence: float = 0.0
    weaknesses: List[str] = field(default_factory=list)
    counter_arguments: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "argument_id": self.argument_id,
            "text": self.text,
            "supporting_precedents": self.supporting_precedents,
            "citations": self.citations,
            "confidence": self.confidence,
            "weaknesses": self.weaknesses,
            "counter_arguments": self.counter_arguments,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""
    turn_id: str
    role: str  # "user", "lawyer", "opponent"
    message: str
    timestamp: datetime
    context: Optional[ArgumentContext] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "turn_id": self.turn_id,
            "role": self.role,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context.to_dict() if self.context else None,
            "metadata": self.metadata
        }


class LegalContext:
    """Manages legal context for a conversation session."""
    
    def __init__(
        self,
        session_id: str,
        case_info: Optional[CaseInfo] = None,
        our_lawyer: Optional[LawyerInfo] = None,
        opposing_counsel: Optional[LawyerInfo] = None
    ):
        """Initialize legal context.
        
        Args:
            session_id: Unique session identifier
            case_info: Information about the case
            our_lawyer: Our lawyer's information
            opposing_counsel: Opposing counsel's information
        """
        self.session_id = session_id
        self.case_info = case_info
        self.our_lawyer = our_lawyer
        self.opposing_counsel = opposing_counsel
        self.conversation_history: List[ConversationTurn] = []
        self.our_arguments: List[ArgumentContext] = []
        self.anticipated_oppositions: List[ArgumentContext] = []
        self.key_precedents: List[Dict[str, Any]] = []
        self.session_metadata: Dict[str, Any] = {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "turn_count": 0
        }
        
    def add_turn(
        self,
        role: str,
        message: str,
        context: Optional[ArgumentContext] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ConversationTurn:
        """Add a conversation turn.
        
        Args:
            role: Role of the speaker
            message: The message content
            context: Optional argument context
            metadata: Optional metadata
            
        Returns:
            The created conversation turn
        """
        turn_id = self._generate_turn_id()
        turn = ConversationTurn(
            turn_id=turn_id,
            role=role,
            message=message,
            timestamp=datetime.now(),
            context=context,
            metadata=metadata or {}
        )
        self.conversation_history.append(turn)
        self.session_metadata["turn_count"] += 1
        self.session_metadata["last_updated"] = datetime.now().isoformat()
        return turn
        
    def add_our_argument(self, argument: ArgumentContext) -> None:
        """Add an argument from our side.
        
        Args:
            argument: The argument context
        """
        self.our_arguments.append(argument)
        
    def add_anticipated_opposition(self, argument: ArgumentContext) -> None:
        """Add an anticipated opposition argument.
        
        Args:
            argument: The anticipated argument
        """
        self.anticipated_oppositions.append(argument)
        
    def add_precedent(self, precedent: Dict[str, Any]) -> None:
        """Add a key precedent.
        
        Args:
            precedent: Precedent information
        """
        self.key_precedents.append(precedent)
        
    def get_recent_history(self, n: int = 10) -> List[ConversationTurn]:
        """Get recent conversation history.
        
        Args:
            n: Number of recent turns to retrieve
            
        Returns:
            List of recent conversation turns
        """
        return self.conversation_history[-n:] if self.conversation_history else []
        
    def get_context_summary(self) -> Dict[str, Any]:
        """Get a summary of the current context.
        
        Returns:
            Dictionary containing context summary
        """
        return {
            "session_id": self.session_id,
            "case_info": self.case_info.to_dict() if self.case_info else None,
            "our_lawyer": self.our_lawyer.to_dict() if self.our_lawyer else None,
            "opposing_counsel": self.opposing_counsel.to_dict() if self.opposing_counsel else None,
            "total_turns": len(self.conversation_history),
            "our_arguments_count": len(self.our_arguments),
            "anticipated_oppositions_count": len(self.anticipated_oppositions),
            "key_precedents_count": len(self.key_precedents),
            "session_metadata": self.session_metadata
        }
        
    def get_argument_history(self) -> Dict[str, List[ArgumentContext]]:
        """Get organized argument history.
        
        Returns:
            Dictionary with our arguments and anticipated oppositions
        """
        return {
            "our_arguments": self.our_arguments,
            "anticipated_oppositions": self.anticipated_oppositions
        }
        
    def find_related_arguments(self, query: str) -> List[ArgumentContext]:
        """Find related arguments from history.
        
        Args:
            query: Search query
            
        Returns:
            List of related arguments
        """
        related = []
        query_lower = query.lower()
        
        # Search in our arguments
        for arg in self.our_arguments:
            if query_lower in arg.text.lower():
                related.append(arg)
                
        # Search in anticipated oppositions
        for arg in self.anticipated_oppositions:
            if query_lower in arg.text.lower():
                related.append(arg)
                
        return related
        
    def clear_history(self) -> None:
        """Clear conversation history while maintaining context."""
        self.conversation_history.clear()
        self.session_metadata["turn_count"] = 0
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert entire context to dictionary.
        
        Returns:
            Dictionary representation of the context
        """
        return {
            "session_id": self.session_id,
            "case_info": self.case_info.to_dict() if self.case_info else None,
            "our_lawyer": self.our_lawyer.to_dict() if self.our_lawyer else None,
            "opposing_counsel": self.opposing_counsel.to_dict() if self.opposing_counsel else None,
            "conversation_history": [turn.to_dict() for turn in self.conversation_history],
            "our_arguments": [arg.to_dict() for arg in self.our_arguments],
            "anticipated_oppositions": [arg.to_dict() for arg in self.anticipated_oppositions],
            "key_precedents": self.key_precedents,
            "session_metadata": self.session_metadata
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LegalContext":
        """Create LegalContext from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            LegalContext instance
        """
        # Parse case info
        case_info = None
        if data.get("case_info"):
            case_data = data["case_info"]
            case_info = CaseInfo(
                case_id=case_data["case_id"],
                caption=case_data["caption"],
                court=case_data["court"],
                jurisdiction=case_data["jurisdiction"],
                case_type=case_data["case_type"],
                filed_date=datetime.fromisoformat(case_data["filed_date"]) if case_data.get("filed_date") else None,
                judge_name=case_data.get("judge_name"),
                judge_id=case_data.get("judge_id"),
                our_role=PartyRole(case_data["our_role"]) if case_data.get("our_role") else None,
                opposing_role=PartyRole(case_data["opposing_role"]) if case_data.get("opposing_role") else None,
                key_issues=case_data.get("key_issues", []),
                current_stage=case_data.get("current_stage")
            )
            
        # Parse lawyer info
        our_lawyer = None
        if data.get("our_lawyer"):
            lawyer_data = data["our_lawyer"]
            our_lawyer = LawyerInfo(
                id=lawyer_data["id"],
                name=lawyer_data["name"],
                firm=lawyer_data.get("firm"),
                bar_id=lawyer_data.get("bar_id"),
                specializations=lawyer_data.get("specializations", []),
                years_experience=lawyer_data.get("years_experience"),
                win_rate=lawyer_data.get("win_rate")
            )
            
        # Parse opposing counsel
        opposing_counsel = None
        if data.get("opposing_counsel"):
            counsel_data = data["opposing_counsel"]
            opposing_counsel = LawyerInfo(
                id=counsel_data["id"],
                name=counsel_data["name"],
                firm=counsel_data.get("firm"),
                bar_id=counsel_data.get("bar_id"),
                specializations=counsel_data.get("specializations", []),
                years_experience=counsel_data.get("years_experience"),
                win_rate=counsel_data.get("win_rate")
            )
            
        # Create context
        context = cls(
            session_id=data["session_id"],
            case_info=case_info,
            our_lawyer=our_lawyer,
            opposing_counsel=opposing_counsel
        )
        
        # Restore session metadata
        if "session_metadata" in data:
            context.session_metadata = data["session_metadata"]
            
        # Restore other data
        context.key_precedents = data.get("key_precedents", [])
        
        return context
        
    def _generate_turn_id(self) -> str:
        """Generate unique turn ID.
        
        Returns:
            Unique turn identifier
        """
        content = f"{self.session_id}_{len(self.conversation_history)}_{datetime.now().isoformat()}"
        return hashlib.md5(content.encode()).hexdigest()[:12]