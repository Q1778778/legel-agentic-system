"""WebSocket manager for real-time debate updates."""

from typing import Dict, Set, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio
from datetime import datetime
from enum import Enum
import structlog

from .base_agent import AgentMessage

logger = structlog.get_logger()


class WebSocketEventType(str, Enum):
    """Types of WebSocket events."""
    CONNECTION = "connection"
    DEBATE_START = "debate_start"
    AGENT_MESSAGE = "agent_message"
    TURN_COMPLETE = "turn_complete"
    DEBATE_END = "debate_end"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class WebSocketEvent:
    """WebSocket event wrapper."""
    
    def __init__(
        self,
        event_type: WebSocketEventType,
        data: Any,
        session_id: Optional[str] = None
    ):
        """Initialize WebSocket event.
        
        Args:
            event_type: Type of event
            data: Event data
            session_id: Optional session ID
        """
        self.event_type = event_type
        self.data = data
        self.session_id = session_id
        self.timestamp = datetime.utcnow().isoformat()
    
    def to_json(self) -> str:
        """Convert event to JSON string.
        
        Returns:
            JSON representation
        """
        return json.dumps({
            "type": self.event_type,
            "data": self.data if isinstance(self.data, dict) else str(self.data),
            "session_id": self.session_id,
            "timestamp": self.timestamp
        })


class ConnectionManager:
    """Manages WebSocket connections for a single debate session."""
    
    def __init__(self, session_id: str):
        """Initialize connection manager.
        
        Args:
            session_id: Unique session identifier
        """
        self.session_id = session_id
        self.active_connections: Set[WebSocket] = set()
        self.message_history: list = []
        self.created_at = datetime.utcnow()
        
    async def connect(self, websocket: WebSocket):
        """Accept and register a new connection.
        
        Args:
            websocket: WebSocket connection
        """
        await websocket.accept()
        self.active_connections.add(websocket)
        
        # Send connection confirmation
        event = WebSocketEvent(
            WebSocketEventType.CONNECTION,
            {"status": "connected", "session_id": self.session_id},
            self.session_id
        )
        await self.send_to_client(websocket, event)
        
        # Send message history to new connection
        if self.message_history:
            for message in self.message_history[-10:]:  # Last 10 messages
                await self.send_to_client(websocket, message)
        
        logger.info(f"Client connected to session {self.session_id}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove a connection.
        
        Args:
            websocket: WebSocket connection to remove
        """
        self.active_connections.discard(websocket)
        logger.info(f"Client disconnected from session {self.session_id}")
    
    async def send_to_client(self, websocket: WebSocket, event: WebSocketEvent):
        """Send event to specific client.
        
        Args:
            websocket: Target WebSocket
            event: Event to send
        """
        try:
            await websocket.send_text(event.to_json())
        except Exception as e:
            logger.error(f"Error sending to client: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, event: WebSocketEvent):
        """Broadcast event to all connected clients.
        
        Args:
            event: Event to broadcast
        """
        # Store in history
        self.message_history.append(event)
        
        # Keep history limited
        if len(self.message_history) > 100:
            self.message_history = self.message_history[-50:]
        
        # Send to all active connections
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(event.to_json())
            except Exception as e:
                logger.error(f"Error broadcasting: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


class WebSocketManager:
    """Global WebSocket manager for all debate sessions."""
    
    def __init__(self):
        """Initialize the WebSocket manager."""
        self.sessions: Dict[str, ConnectionManager] = {}
        self._cleanup_task = None
        
    def create_session(self, session_id: str) -> ConnectionManager:
        """Create a new debate session.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Connection manager for the session
        """
        if session_id in self.sessions:
            logger.warning(f"Session {session_id} already exists")
            return self.sessions[session_id]
        
        manager = ConnectionManager(session_id)
        self.sessions[session_id] = manager
        
        logger.info(f"Created session: {session_id}")
        return manager
    
    def get_session(self, session_id: str) -> Optional[ConnectionManager]:
        """Get a session by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Connection manager or None
        """
        return self.sessions.get(session_id)
    
    async def connect_to_session(
        self,
        websocket: WebSocket,
        session_id: str
    ) -> ConnectionManager:
        """Connect a client to a session.
        
        Args:
            websocket: WebSocket connection
            session_id: Session to join
            
        Returns:
            Connection manager for the session
        """
        # Create session if it doesn't exist
        if session_id not in self.sessions:
            self.create_session(session_id)
        
        manager = self.sessions[session_id]
        await manager.connect(websocket)
        
        return manager
    
    async def broadcast_debate_start(
        self,
        session_id: str,
        case_id: str,
        issue_text: str,
        mode: str
    ):
        """Broadcast debate start event.
        
        Args:
            session_id: Session ID
            case_id: Case identifier
            issue_text: Legal issue
            mode: Debate mode
        """
        manager = self.get_session(session_id)
        if not manager:
            return
        
        event = WebSocketEvent(
            WebSocketEventType.DEBATE_START,
            {
                "case_id": case_id,
                "issue": issue_text,
                "mode": mode,
                "started_at": datetime.utcnow().isoformat()
            },
            session_id
        )
        
        await manager.broadcast(event)
    
    async def broadcast_agent_message(
        self,
        session_id: str,
        message: AgentMessage
    ):
        """Broadcast an agent message.
        
        Args:
            session_id: Session ID
            message: Agent message to broadcast
        """
        manager = self.get_session(session_id)
        if not manager:
            return
        
        event = WebSocketEvent(
            WebSocketEventType.AGENT_MESSAGE,
            {
                "role": message.role,
                "content": message.content,
                "citations": message.citations,
                "confidence": message.confidence,
                "metadata": message.metadata
            },
            session_id
        )
        
        await manager.broadcast(event)
    
    async def broadcast_turn_complete(
        self,
        session_id: str,
        turn_number: int,
        messages: list
    ):
        """Broadcast turn completion.
        
        Args:
            session_id: Session ID
            turn_number: Turn number
            messages: Messages from this turn
        """
        manager = self.get_session(session_id)
        if not manager:
            return
        
        event = WebSocketEvent(
            WebSocketEventType.TURN_COMPLETE,
            {
                "turn": turn_number,
                "message_count": len(messages),
                "roles": [msg.role for msg in messages]
            },
            session_id
        )
        
        await manager.broadcast(event)
    
    async def broadcast_debate_end(
        self,
        session_id: str,
        summary: Dict[str, Any]
    ):
        """Broadcast debate end event.
        
        Args:
            session_id: Session ID
            summary: Debate summary
        """
        manager = self.get_session(session_id)
        if not manager:
            return
        
        event = WebSocketEvent(
            WebSocketEventType.DEBATE_END,
            summary,
            session_id
        )
        
        await manager.broadcast(event)
    
    async def broadcast_error(
        self,
        session_id: str,
        error: str
    ):
        """Broadcast error event.
        
        Args:
            session_id: Session ID
            error: Error message
        """
        manager = self.get_session(session_id)
        if not manager:
            return
        
        event = WebSocketEvent(
            WebSocketEventType.ERROR,
            {"error": error},
            session_id
        )
        
        await manager.broadcast(event)
    
    async def send_heartbeat(self, session_id: str):
        """Send heartbeat to keep connections alive.
        
        Args:
            session_id: Session ID
        """
        manager = self.get_session(session_id)
        if not manager:
            return
        
        event = WebSocketEvent(
            WebSocketEventType.HEARTBEAT,
            {"timestamp": datetime.utcnow().isoformat()},
            session_id
        )
        
        await manager.broadcast(event)
    
    async def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Clean up old sessions.
        
        Args:
            max_age_hours: Maximum session age in hours
        """
        current_time = datetime.utcnow()
        to_remove = []
        
        for session_id, manager in self.sessions.items():
            age_hours = (current_time - manager.created_at).total_seconds() / 3600
            
            # Remove old sessions with no active connections
            if age_hours > max_age_hours and not manager.active_connections:
                to_remove.append(session_id)
        
        for session_id in to_remove:
            del self.sessions[session_id]
            logger.info(f"Cleaned up old session: {session_id}")
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old sessions")
    
    async def start_cleanup_task(self):
        """Start background cleanup task."""
        async def cleanup_loop():
            while True:
                await asyncio.sleep(3600)  # Run every hour
                await self.cleanup_old_sessions()
        
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(cleanup_loop())
    
    def stop_cleanup_task(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None


# Global WebSocket manager instance
ws_manager = WebSocketManager()