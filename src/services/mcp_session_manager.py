"""
MCP Session Manager
Production-ready session management for MCP connections.
"""

import asyncio
import json
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import uuid
from enum import Enum
import pickle
try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None  # Will use memory backend if Redis not available
from contextlib import asynccontextmanager

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class SessionState(str, Enum):
    """Session states."""
    ACTIVE = "active"
    IDLE = "idle"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class StorageBackend(str, Enum):
    """Storage backend types."""
    MEMORY = "memory"
    REDIS = "redis"


@dataclass
class MCPSession:
    """MCP session data."""
    session_id: str
    client_id: str
    created_at: datetime
    last_activity: datetime
    state: SessionState
    metadata: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    
    def is_expired(self, timeout_seconds: int = 3600) -> bool:
        """Check if session is expired."""
        return (datetime.now() - self.last_activity).seconds > timeout_seconds
        
    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.now()
        
    def add_to_history(self, entry: Dict[str, Any]):
        """Add entry to session history."""
        entry["timestamp"] = datetime.now().isoformat()
        self.history.append(entry)
        
        # Limit history size
        if len(self.history) > 1000:
            self.history = self.history[-500:]  # Keep last 500 entries
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary."""
        return {
            "session_id": self.session_id,
            "client_id": self.client_id,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "state": self.state.value,
            "metadata": self.metadata,
            "context": self.context,
            "history_count": len(self.history)
        }


class SessionStorage:
    """Abstract base class for session storage."""
    
    async def get(self, session_id: str) -> Optional[MCPSession]:
        """Get session by ID."""
        raise NotImplementedError
        
    async def set(self, session: MCPSession):
        """Store session."""
        raise NotImplementedError
        
    async def delete(self, session_id: str):
        """Delete session."""
        raise NotImplementedError
        
    async def list_sessions(self, client_id: Optional[str] = None) -> List[str]:
        """List session IDs."""
        raise NotImplementedError
        
    async def cleanup_expired(self, timeout_seconds: int):
        """Clean up expired sessions."""
        raise NotImplementedError


class MemorySessionStorage(SessionStorage):
    """In-memory session storage."""
    
    def __init__(self):
        self.sessions: Dict[str, MCPSession] = {}
        self.client_sessions: Dict[str, Set[str]] = {}
        
    async def get(self, session_id: str) -> Optional[MCPSession]:
        """Get session by ID."""
        return self.sessions.get(session_id)
        
    async def set(self, session: MCPSession):
        """Store session."""
        self.sessions[session.session_id] = session
        
        # Track by client
        if session.client_id not in self.client_sessions:
            self.client_sessions[session.client_id] = set()
        self.client_sessions[session.client_id].add(session.session_id)
        
    async def delete(self, session_id: str):
        """Delete session."""
        session = self.sessions.pop(session_id, None)
        if session and session.client_id in self.client_sessions:
            self.client_sessions[session.client_id].discard(session_id)
            
    async def list_sessions(self, client_id: Optional[str] = None) -> List[str]:
        """List session IDs."""
        if client_id:
            return list(self.client_sessions.get(client_id, set()))
        return list(self.sessions.keys())
        
    async def cleanup_expired(self, timeout_seconds: int):
        """Clean up expired sessions."""
        expired_ids = [
            sid for sid, session in self.sessions.items()
            if session.is_expired(timeout_seconds)
        ]
        
        for session_id in expired_ids:
            await self.delete(session_id)
            
        return len(expired_ids)


class RedisSessionStorage(SessionStorage):
    """Redis-based session storage."""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis: Optional[aioredis.Redis] = None
        self.key_prefix = "mcp:session:"
        self.client_prefix = "mcp:client:"
        
    async def connect(self):
        """Connect to Redis."""
        if not self.redis:
            self.redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=False
            )
            
    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            self.redis = None
            
    async def get(self, session_id: str) -> Optional[MCPSession]:
        """Get session by ID."""
        await self.connect()
        
        key = f"{self.key_prefix}{session_id}"
        data = await self.redis.get(key)
        
        if data:
            try:
                return pickle.loads(data)
            except Exception as e:
                logger.error(f"Failed to deserialize session: {e}")
                return None
                
        return None
        
    async def set(self, session: MCPSession):
        """Store session with TTL."""
        await self.connect()
        
        # Store session
        key = f"{self.key_prefix}{session.session_id}"
        data = pickle.dumps(session)
        await self.redis.set(key, data, ex=7200)  # 2 hour TTL
        
        # Track by client
        client_key = f"{self.client_prefix}{session.client_id}"
        await self.redis.sadd(client_key, session.session_id)
        await self.redis.expire(client_key, 7200)
        
    async def delete(self, session_id: str):
        """Delete session."""
        await self.connect()
        
        # Get session first to remove from client set
        session = await self.get(session_id)
        if session:
            client_key = f"{self.client_prefix}{session.client_id}"
            await self.redis.srem(client_key, session_id)
            
        # Delete session
        key = f"{self.key_prefix}{session_id}"
        await self.redis.delete(key)
        
    async def list_sessions(self, client_id: Optional[str] = None) -> List[str]:
        """List session IDs."""
        await self.connect()
        
        if client_id:
            client_key = f"{self.client_prefix}{client_id}"
            members = await self.redis.smembers(client_key)
            return [m.decode() if isinstance(m, bytes) else m for m in members]
        else:
            # List all sessions (expensive operation)
            pattern = f"{self.key_prefix}*"
            keys = await self.redis.keys(pattern)
            return [k.decode().replace(self.key_prefix, "") for k in keys]
            
    async def cleanup_expired(self, timeout_seconds: int):
        """Clean up expired sessions."""
        # Redis handles TTL automatically
        # This method can be used for additional cleanup if needed
        return 0


class MCPSessionManager:
    """Manages MCP sessions with configurable storage backend."""
    
    def __init__(
        self,
        storage_backend: StorageBackend = StorageBackend.MEMORY,
        redis_url: Optional[str] = None,
        session_timeout: int = 3600,
        max_sessions_per_client: int = 10
    ):
        self.storage_backend = storage_backend
        self.session_timeout = session_timeout
        self.max_sessions_per_client = max_sessions_per_client
        
        # Initialize storage
        if storage_backend == StorageBackend.REDIS:
            if not redis_url:
                raise ValueError("Redis URL required for Redis backend")
            self.storage = RedisSessionStorage(redis_url)
        else:
            self.storage = MemorySessionStorage()
            
        # Cleanup task
        self.cleanup_task: Optional[asyncio.Task] = None
        
    async def initialize(self):
        """Initialize the session manager."""
        logger.info(f"Initializing session manager with {self.storage_backend} backend")
        
        # Connect to storage if needed
        if isinstance(self.storage, RedisSessionStorage):
            await self.storage.connect()
            
        # Start cleanup task
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
    async def shutdown(self):
        """Shutdown the session manager."""
        logger.info("Shutting down session manager")
        
        # Cancel cleanup task
        if self.cleanup_task:
            self.cleanup_task.cancel()
            
        # Disconnect from storage
        if isinstance(self.storage, RedisSessionStorage):
            await self.storage.disconnect()
            
    async def create_session(
        self,
        client_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> MCPSession:
        """Create a new session."""
        # Check session limit for client
        existing_sessions = await self.storage.list_sessions(client_id)
        if len(existing_sessions) >= self.max_sessions_per_client:
            # Remove oldest session
            oldest_session_id = existing_sessions[0]
            await self.destroy_session(oldest_session_id)
            logger.warning(f"Removed oldest session for client {client_id} due to limit")
            
        # Create new session
        session = MCPSession(
            session_id=str(uuid.uuid4()),
            client_id=client_id,
            created_at=datetime.now(),
            last_activity=datetime.now(),
            state=SessionState.ACTIVE,
            metadata=metadata or {}
        )
        
        # Store session
        await self.storage.set(session)
        
        logger.info(f"Created session {session.session_id} for client {client_id}")
        return session
        
    async def get_session(self, session_id: str) -> Optional[MCPSession]:
        """Get session by ID."""
        session = await self.storage.get(session_id)
        
        if session:
            # Check if expired
            if session.is_expired(self.session_timeout):
                session.state = SessionState.EXPIRED
                await self.storage.set(session)
                logger.warning(f"Session {session_id} has expired")
            else:
                # Update activity
                session.update_activity()
                await self.storage.set(session)
                
        return session
        
    async def update_session(self, session: MCPSession):
        """Update session data."""
        session.update_activity()
        await self.storage.set(session)
        
    async def destroy_session(self, session_id: str):
        """Destroy a session."""
        session = await self.storage.get(session_id)
        if session:
            session.state = SessionState.TERMINATED
            await self.storage.set(session)
            
        await self.storage.delete(session_id)
        logger.info(f"Destroyed session {session_id}")
        
    async def list_client_sessions(self, client_id: str) -> List[MCPSession]:
        """List all sessions for a client."""
        session_ids = await self.storage.list_sessions(client_id)
        sessions = []
        
        for session_id in session_ids:
            session = await self.storage.get(session_id)
            if session:
                sessions.append(session)
                
        return sessions
        
    async def add_to_history(
        self,
        session_id: str,
        entry_type: str,
        data: Dict[str, Any]
    ):
        """Add entry to session history."""
        session = await self.get_session(session_id)
        if session:
            session.add_to_history({
                "type": entry_type,
                "data": data
            })
            await self.storage.set(session)
            
    async def update_context(
        self,
        session_id: str,
        context_updates: Dict[str, Any]
    ):
        """Update session context."""
        session = await self.get_session(session_id)
        if session:
            session.context.update(context_updates)
            await self.storage.set(session)
            
    def get_status(self) -> Dict[str, Any]:
        """Get session manager status."""
        return {
            "backend": self.storage_backend.value,
            "session_timeout": self.session_timeout,
            "max_sessions_per_client": self.max_sessions_per_client
        }
        
    async def _cleanup_loop(self):
        """Periodic cleanup of expired sessions."""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                
                cleaned = await self.storage.cleanup_expired(self.session_timeout)
                if cleaned > 0:
                    logger.info(f"Cleaned up {cleaned} expired sessions")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                
    @asynccontextmanager
    async def session_context(self, client_id: str):
        """Context manager for session lifecycle."""
        session = await self.create_session(client_id)
        try:
            yield session
        finally:
            await self.destroy_session(session.session_id)


# Singleton instance
_session_manager: Optional[MCPSessionManager] = None


def get_session_manager() -> MCPSessionManager:
    """Get the singleton session manager instance."""
    global _session_manager
    if _session_manager is None:
        # Default to memory storage
        _session_manager = MCPSessionManager(
            storage_backend=StorageBackend.MEMORY,
            session_timeout=3600,
            max_sessions_per_client=10
        )
    return _session_manager


def configure_session_manager(
    storage_backend: StorageBackend = StorageBackend.MEMORY,
    redis_url: Optional[str] = None,
    session_timeout: int = 3600,
    max_sessions_per_client: int = 10
) -> MCPSessionManager:
    """Configure and get session manager."""
    global _session_manager
    _session_manager = MCPSessionManager(
        storage_backend=storage_backend,
        redis_url=redis_url,
        session_timeout=session_timeout,
        max_sessions_per_client=max_sessions_per_client
    )
    return _session_manager