"""Conversation session management for the MCP lawyer server."""

import asyncio
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
import hashlib
import json
from collections import OrderedDict
import structlog

from .legal_context import LegalContext, CaseInfo, LawyerInfo, ArgumentContext

logger = structlog.get_logger()


class ConversationSession:
    """Individual conversation session."""
    
    def __init__(
        self,
        session_id: str,
        context: LegalContext,
        ttl: int = 3600
    ):
        """Initialize conversation session.
        
        Args:
            session_id: Unique session identifier
            context: Legal context for the session
            ttl: Time to live in seconds
        """
        self.session_id = session_id
        self.context = context
        self.created_at = datetime.now()
        self.last_accessed = datetime.now()
        self.ttl = ttl
        self.is_active = True
        self.metadata: Dict[str, Any] = {}
        
    def touch(self) -> None:
        """Update last accessed time."""
        self.last_accessed = datetime.now()
        
    def is_expired(self) -> bool:
        """Check if session has expired.
        
        Returns:
            True if session has expired
        """
        if not self.is_active:
            return True
        elapsed = (datetime.now() - self.last_accessed).total_seconds()
        return elapsed > self.ttl
        
    def deactivate(self) -> None:
        """Deactivate the session."""
        self.is_active = False
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "ttl": self.ttl,
            "is_active": self.is_active,
            "context_summary": self.context.get_context_summary(),
            "metadata": self.metadata
        }


class ConversationManager:
    """Manages multiple conversation sessions."""
    
    def __init__(
        self,
        max_sessions: int = 1000,
        session_ttl: int = 3600,
        max_history_per_session: int = 100,
        cleanup_interval: int = 300
    ):
        """Initialize conversation manager.
        
        Args:
            max_sessions: Maximum number of concurrent sessions
            session_ttl: Session time to live in seconds
            max_history_per_session: Maximum conversation turns per session
            cleanup_interval: Interval for cleanup task in seconds
        """
        self.sessions: OrderedDict[str, ConversationSession] = OrderedDict()
        self.max_sessions = max_sessions
        self.session_ttl = session_ttl
        self.max_history_per_session = max_history_per_session
        self.cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
    async def start(self) -> None:
        """Start the conversation manager."""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Conversation manager started")
            
    async def stop(self) -> None:
        """Stop the conversation manager."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Conversation manager stopped")
            
    async def create_session(
        self,
        case_info: Optional[CaseInfo] = None,
        our_lawyer: Optional[LawyerInfo] = None,
        opposing_counsel: Optional[LawyerInfo] = None,
        session_id: Optional[str] = None
    ) -> ConversationSession:
        """Create a new conversation session.
        
        Args:
            case_info: Case information
            our_lawyer: Our lawyer's information
            opposing_counsel: Opposing counsel's information
            session_id: Optional session ID (will be generated if not provided)
            
        Returns:
            Created conversation session
            
        Raises:
            ValueError: If max sessions limit reached
        """
        async with self._lock:
            # Check session limit
            if len(self.sessions) >= self.max_sessions:
                # Try to remove expired sessions first
                await self._cleanup_expired_sessions()
                if len(self.sessions) >= self.max_sessions:
                    # Remove oldest session
                    oldest_id = next(iter(self.sessions))
                    del self.sessions[oldest_id]
                    logger.warning(f"Removed oldest session {oldest_id} due to limit")
                    
            # Generate session ID if not provided
            if not session_id:
                session_id = self._generate_session_id()
                
            # Create legal context
            context = LegalContext(
                session_id=session_id,
                case_info=case_info,
                our_lawyer=our_lawyer,
                opposing_counsel=opposing_counsel
            )
            
            # Create session
            session = ConversationSession(
                session_id=session_id,
                context=context,
                ttl=self.session_ttl
            )
            
            # Store session
            self.sessions[session_id] = session
            # Move to end to maintain LRU order
            self.sessions.move_to_end(session_id)
            
            logger.info(f"Created session {session_id}")
            return session
            
    async def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session if found and active, None otherwise
        """
        async with self._lock:
            session = self.sessions.get(session_id)
            if session:
                if session.is_expired():
                    del self.sessions[session_id]
                    logger.info(f"Session {session_id} expired and removed")
                    return None
                session.touch()
                # Move to end for LRU
                self.sessions.move_to_end(session_id)
                return session
            return None
            
    async def update_session_context(
        self,
        session_id: str,
        case_info: Optional[CaseInfo] = None,
        our_lawyer: Optional[LawyerInfo] = None,
        opposing_counsel: Optional[LawyerInfo] = None
    ) -> bool:
        """Update session context information.
        
        Args:
            session_id: Session identifier
            case_info: Updated case information
            our_lawyer: Updated lawyer information
            opposing_counsel: Updated opposing counsel information
            
        Returns:
            True if session was updated, False if not found
        """
        session = await self.get_session(session_id)
        if not session:
            return False
            
        if case_info:
            session.context.case_info = case_info
        if our_lawyer:
            session.context.our_lawyer = our_lawyer
        if opposing_counsel:
            session.context.opposing_counsel = opposing_counsel
            
        session.touch()
        logger.info(f"Updated context for session {session_id}")
        return True
        
    async def add_conversation_turn(
        self,
        session_id: str,
        role: str,
        message: str,
        context: Optional[ArgumentContext] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add a conversation turn to a session.
        
        Args:
            session_id: Session identifier
            role: Role of the speaker
            message: Message content
            context: Optional argument context
            metadata: Optional metadata
            
        Returns:
            True if turn was added, False if session not found
        """
        session = await self.get_session(session_id)
        if not session:
            return False
            
        # Check history limit
        if len(session.context.conversation_history) >= self.max_history_per_session:
            # Remove oldest turn
            session.context.conversation_history.pop(0)
            logger.debug(f"Trimmed conversation history for session {session_id}")
            
        session.context.add_turn(role, message, context, metadata)
        session.touch()
        return True
        
    async def get_session_history(
        self,
        session_id: str,
        n: Optional[int] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Get conversation history for a session.
        
        Args:
            session_id: Session identifier
            n: Number of recent turns to retrieve (None for all)
            
        Returns:
            List of conversation turns if session found, None otherwise
        """
        session = await self.get_session(session_id)
        if not session:
            return None
            
        if n:
            turns = session.context.get_recent_history(n)
        else:
            turns = session.context.conversation_history
            
        return [turn.to_dict() for turn in turns]
        
    async def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get summary of a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session summary if found, None otherwise
        """
        session = await self.get_session(session_id)
        if not session:
            return None
            
        return session.context.get_context_summary()
        
    async def list_active_sessions(self) -> List[Dict[str, Any]]:
        """List all active sessions.
        
        Returns:
            List of active session summaries
        """
        async with self._lock:
            active_sessions = []
            for session in self.sessions.values():
                if not session.is_expired():
                    active_sessions.append({
                        "session_id": session.session_id,
                        "created_at": session.created_at.isoformat(),
                        "last_accessed": session.last_accessed.isoformat(),
                        "is_active": session.is_active,
                        "case_caption": session.context.case_info.caption if session.context.case_info else None
                    })
            return active_sessions
            
    async def end_session(self, session_id: str) -> bool:
        """End a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if session was ended, False if not found
        """
        async with self._lock:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                session.deactivate()
                del self.sessions[session_id]
                logger.info(f"Ended session {session_id}")
                return True
            return False
            
    async def export_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Export session data.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Complete session data if found, None otherwise
        """
        session = await self.get_session(session_id)
        if not session:
            return None
            
        return {
            "session": session.to_dict(),
            "context": session.context.to_dict()
        }
        
    async def import_session(
        self,
        session_data: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> Optional[ConversationSession]:
        """Import session data.
        
        Args:
            session_data: Session data to import
            session_id: Optional session ID override
            
        Returns:
            Imported session if successful, None otherwise
        """
        try:
            context_data = session_data.get("context")
            if not context_data:
                return None
                
            # Create context from data
            context = LegalContext.from_dict(context_data)
            
            # Override session ID if provided
            if session_id:
                context.session_id = session_id
            else:
                session_id = context.session_id
                
            # Create session
            async with self._lock:
                if len(self.sessions) >= self.max_sessions:
                    await self._cleanup_expired_sessions()
                    
                session = ConversationSession(
                    session_id=session_id,
                    context=context,
                    ttl=self.session_ttl
                )
                
                # Restore metadata if available
                if "session" in session_data:
                    session_meta = session_data["session"]
                    if "metadata" in session_meta:
                        session.metadata = session_meta["metadata"]
                        
                self.sessions[session_id] = session
                self.sessions.move_to_end(session_id)
                
                logger.info(f"Imported session {session_id}")
                return session
                
        except Exception as e:
            logger.error(f"Failed to import session: {e}")
            return None
            
    async def _cleanup_expired_sessions(self) -> None:
        """Remove expired sessions."""
        expired = []
        for session_id, session in self.sessions.items():
            if session.is_expired():
                expired.append(session_id)
                
        for session_id in expired:
            del self.sessions[session_id]
            
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")
            
    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                async with self._lock:
                    await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                
    def _generate_session_id(self) -> str:
        """Generate unique session ID.
        
        Returns:
            Unique session identifier
        """
        content = f"{datetime.now().isoformat()}_{len(self.sessions)}"
        return f"session_{hashlib.md5(content.encode()).hexdigest()[:16]}"
        
    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics.
        
        Returns:
            Statistics dictionary
        """
        active_count = sum(1 for s in self.sessions.values() if not s.is_expired())
        total_turns = sum(
            len(s.context.conversation_history) 
            for s in self.sessions.values()
        )
        
        return {
            "total_sessions": len(self.sessions),
            "active_sessions": active_count,
            "expired_sessions": len(self.sessions) - active_count,
            "total_conversation_turns": total_turns,
            "max_sessions": self.max_sessions,
            "session_ttl": self.session_ttl,
            "cleanup_interval": self.cleanup_interval
        }