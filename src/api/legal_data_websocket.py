"""
WebSocket endpoints for real-time legal data streaming and updates.

This module provides WebSocket connections for:
- Real-time legal data search results
- Live indexing progress updates
- Streaming API data ingestion
- Collaborative legal research sessions
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, asdict
from enum import Enum
import structlog
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from ..services.legal_data_apis import LegalDataAPIClient, DataSource
from ..services.legal_data_processor import LegalDataProcessor
from ..services.legal_data_indexer import LegalDataIndexer
from ..db.graph_db import GraphDB
from ..db.vector_db import VectorDB
from ..services.embeddings import EmbeddingService

logger = structlog.get_logger()


class MessageType(Enum):
    """Types of WebSocket messages."""
    # Client to server
    SEARCH_REQUEST = "search_request"
    START_INDEXING = "start_indexing"
    STOP_INDEXING = "stop_indexing"
    JOIN_SESSION = "join_session"
    LEAVE_SESSION = "leave_session"
    
    # Server to client
    SEARCH_RESULT = "search_result"
    SEARCH_PROGRESS = "search_progress"
    SEARCH_COMPLETE = "search_complete"
    INDEXING_PROGRESS = "indexing_progress"
    INDEXING_COMPLETE = "indexing_complete"
    SESSION_UPDATE = "session_update"
    ERROR = "error"
    STATUS = "status"


@dataclass
class WebSocketMessage:
    """Standard WebSocket message format."""
    type: str
    data: Dict[str, Any]
    timestamp: str
    message_id: Optional[str] = None
    session_id: Optional[str] = None


class SearchRequest(BaseModel):
    """Search request from client."""
    query: str
    sources: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None
    limit: int = 20
    stream_results: bool = True


class IndexingRequest(BaseModel):
    """Indexing request from client."""
    query: str
    sources: Optional[List[str]] = None
    limit: int = 100
    batch_size: int = 10


class SessionJoinRequest(BaseModel):
    """Session join request."""
    session_id: str
    user_id: str
    user_name: Optional[str] = None


class ConnectionManager:
    """Manages WebSocket connections and sessions."""
    
    def __init__(self):
        """Initialize connection manager."""
        # Active connections by connection ID
        self.connections: Dict[str, WebSocket] = {}
        
        # Sessions for collaborative research
        self.sessions: Dict[str, Set[str]] = {}
        
        # Connection metadata
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        
        # Active tasks for each connection
        self.active_tasks: Dict[str, List[asyncio.Task]] = {}
        
        self.logger = logger
    
    async def connect(self, websocket: WebSocket, connection_id: str):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.connections[connection_id] = websocket
        self.connection_metadata[connection_id] = {
            'connected_at': datetime.now(timezone.utc).isoformat(),
            'user_id': None,
            'session_id': None
        }
        self.active_tasks[connection_id] = []
        
        self.logger.info(f"WebSocket connected: {connection_id}")
        
        # Send welcome message
        await self.send_message(connection_id, MessageType.STATUS, {
            'status': 'connected',
            'connection_id': connection_id,
            'server_time': datetime.now(timezone.utc).isoformat()
        })
    
    async def disconnect(self, connection_id: str):
        """Handle WebSocket disconnection."""
        if connection_id in self.connections:
            # Cancel active tasks
            if connection_id in self.active_tasks:
                for task in self.active_tasks[connection_id]:
                    if not task.done():
                        task.cancel()
                del self.active_tasks[connection_id]
            
            # Remove from sessions
            metadata = self.connection_metadata.get(connection_id, {})
            session_id = metadata.get('session_id')
            if session_id and session_id in self.sessions:
                self.sessions[session_id].discard(connection_id)
                if not self.sessions[session_id]:
                    del self.sessions[session_id]
                else:
                    # Notify other session members
                    await self.broadcast_to_session(session_id, MessageType.SESSION_UPDATE, {
                        'action': 'user_left',
                        'user_id': metadata.get('user_id'),
                        'connection_id': connection_id
                    })
            
            # Clean up
            del self.connections[connection_id]
            if connection_id in self.connection_metadata:
                del self.connection_metadata[connection_id]
            
            self.logger.info(f"WebSocket disconnected: {connection_id}")
    
    async def send_message(self, connection_id: str, message_type: MessageType, data: Dict[str, Any]):
        """Send message to a specific connection."""
        if connection_id not in self.connections:
            return
        
        message = WebSocketMessage(
            type=message_type.value,
            data=data,
            timestamp=datetime.now(timezone.utc).isoformat(),
            message_id=f"{connection_id}_{datetime.now().timestamp()}"
        )
        
        try:
            websocket = self.connections[connection_id]
            await websocket.send_text(json.dumps(asdict(message)))
        except Exception as e:
            self.logger.error(f"Error sending message to {connection_id}: {e}")
            # Connection might be dead, remove it
            await self.disconnect(connection_id)
    
    async def broadcast_to_session(self, session_id: str, message_type: MessageType, data: Dict[str, Any]):
        """Broadcast message to all connections in a session."""
        if session_id not in self.sessions:
            return
        
        tasks = []
        for connection_id in self.sessions[session_id].copy():
            task = self.send_message(connection_id, message_type, data)
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def join_session(self, connection_id: str, session_id: str, user_id: str, user_name: Optional[str] = None):
        """Add connection to a collaborative session."""
        if connection_id not in self.connections:
            return
        
        # Leave current session if any
        current_metadata = self.connection_metadata.get(connection_id, {})
        current_session = current_metadata.get('session_id')
        if current_session and current_session in self.sessions:
            self.sessions[current_session].discard(connection_id)
        
        # Join new session
        if session_id not in self.sessions:
            self.sessions[session_id] = set()
        
        self.sessions[session_id].add(connection_id)
        self.connection_metadata[connection_id].update({
            'session_id': session_id,
            'user_id': user_id,
            'user_name': user_name
        })
        
        # Notify session members
        await self.broadcast_to_session(session_id, MessageType.SESSION_UPDATE, {
            'action': 'user_joined',
            'user_id': user_id,
            'user_name': user_name,
            'connection_id': connection_id,
            'session_members': len(self.sessions[session_id])
        })
        
        self.logger.info(f"Connection {connection_id} joined session {session_id}")
    
    def add_task(self, connection_id: str, task: asyncio.Task):
        """Add a task for a connection."""
        if connection_id in self.active_tasks:
            self.active_tasks[connection_id].append(task)
    
    def get_connection_count(self) -> int:
        """Get total number of active connections."""
        return len(self.connections)
    
    def get_session_count(self) -> int:
        """Get total number of active sessions."""
        return len(self.sessions)


class LegalDataWebSocketHandler:
    """Handles WebSocket messages for legal data operations."""
    
    def __init__(self):
        """Initialize WebSocket handler."""
        self.connection_manager = ConnectionManager()
        self.api_client = LegalDataAPIClient()
        self.processor = LegalDataProcessor()
        self.indexer = LegalDataIndexer(
            graph_db=GraphDB(),
            vector_db=VectorDB(),
            embedding_service=EmbeddingService()
        )
        self.logger = logger
    
    async def handle_connection(self, websocket: WebSocket, connection_id: str):
        """Handle a WebSocket connection."""
        await self.connection_manager.connect(websocket, connection_id)
        
        try:
            while True:
                # Receive message
                data = await websocket.receive_text()
                
                try:
                    message_data = json.loads(data)
                    message_type = message_data.get('type')
                    message_content = message_data.get('data', {})
                    
                    # Route message to appropriate handler
                    if message_type == MessageType.SEARCH_REQUEST.value:
                        await self.handle_search_request(connection_id, message_content)
                    elif message_type == MessageType.START_INDEXING.value:
                        await self.handle_indexing_request(connection_id, message_content)
                    elif message_type == MessageType.STOP_INDEXING.value:
                        await self.handle_stop_indexing(connection_id)
                    elif message_type == MessageType.JOIN_SESSION.value:
                        await self.handle_join_session(connection_id, message_content)
                    elif message_type == MessageType.LEAVE_SESSION.value:
                        await self.handle_leave_session(connection_id)
                    else:
                        await self.connection_manager.send_message(
                            connection_id, MessageType.ERROR, 
                            {'error': f'Unknown message type: {message_type}'}
                        )
                
                except json.JSONDecodeError:
                    await self.connection_manager.send_message(
                        connection_id, MessageType.ERROR,
                        {'error': 'Invalid JSON message format'}
                    )
                except ValidationError as e:
                    await self.connection_manager.send_message(
                        connection_id, MessageType.ERROR,
                        {'error': f'Invalid message data: {str(e)}'}
                    )
                
        except WebSocketDisconnect:
            await self.connection_manager.disconnect(connection_id)
        except Exception as e:
            self.logger.error(f"WebSocket error for {connection_id}: {e}")
            await self.connection_manager.disconnect(connection_id)
    
    async def handle_search_request(self, connection_id: str, data: Dict[str, Any]):
        """Handle streaming search request."""
        try:
            # Validate request
            search_request = SearchRequest(**data)
            
            # Start search task
            search_task = asyncio.create_task(
                self.stream_search_results(connection_id, search_request)
            )
            self.connection_manager.add_task(connection_id, search_task)
            
        except ValidationError as e:
            await self.connection_manager.send_message(
                connection_id, MessageType.ERROR,
                {'error': f'Invalid search request: {str(e)}'}
            )
    
    async def stream_search_results(self, connection_id: str, search_request: SearchRequest):
        """Stream search results to client."""
        try:
            # Send search started message
            await self.connection_manager.send_message(
                connection_id, MessageType.SEARCH_PROGRESS,
                {
                    'status': 'started',
                    'query': search_request.query,
                    'sources': search_request.sources,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
            
            # Convert sources to enum
            sources = None
            if search_request.sources:
                sources = []
                for source_str in search_request.sources:
                    try:
                        sources.append(DataSource(source_str.lower()))
                    except ValueError:
                        await self.connection_manager.send_message(
                            connection_id, MessageType.ERROR,
                            {'error': f'Invalid source: {source_str}'}
                        )
                        return
            
            # Search cases
            if not sources or any(s in [DataSource.COURTLISTENER, DataSource.CAP] for s in sources):
                await self.connection_manager.send_message(
                    connection_id, MessageType.SEARCH_PROGRESS,
                    {'status': 'searching_cases', 'stage': 'Searching legal cases...'}
                )
                
                cases = await self.api_client.search_cases(
                    query=search_request.query,
                    sources=sources,
                    limit=search_request.limit
                )
                
                # Stream case results
                for i, case in enumerate(cases):
                    await self.connection_manager.send_message(
                        connection_id, MessageType.SEARCH_RESULT,
                        {
                            'result_type': 'case',
                            'result_index': i,
                            'data': case.dict(),
                            'total_results': len(cases)
                        }
                    )
                    
                    # Small delay to allow for real-time feeling
                    await asyncio.sleep(0.1)
            
            # Search regulations
            if not sources or any(s in [DataSource.GOVINFO, DataSource.ECFR] for s in sources):
                await self.connection_manager.send_message(
                    connection_id, MessageType.SEARCH_PROGRESS,
                    {'status': 'searching_regulations', 'stage': 'Searching regulations...'}
                )
                
                regulations = await self.api_client.get_regulations(
                    query=search_request.query,
                    limit=search_request.limit
                )
                
                # Stream regulation results
                for i, reg in enumerate(regulations):
                    await self.connection_manager.send_message(
                        connection_id, MessageType.SEARCH_RESULT,
                        {
                            'result_type': 'regulation',
                            'result_index': i,
                            'data': reg.dict(),
                            'total_results': len(regulations)
                        }
                    )
                    
                    await asyncio.sleep(0.1)
            
            # Search complete
            await self.connection_manager.send_message(
                connection_id, MessageType.SEARCH_COMPLETE,
                {
                    'status': 'completed',
                    'query': search_request.query,
                    'total_execution_time_ms': 0,  # Would calculate actual time
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error in stream search: {e}")
            await self.connection_manager.send_message(
                connection_id, MessageType.ERROR,
                {'error': f'Search failed: {str(e)}'}
            )
    
    async def handle_indexing_request(self, connection_id: str, data: Dict[str, Any]):
        """Handle real-time indexing request."""
        try:
            # Validate request
            indexing_request = IndexingRequest(**data)
            
            # Start indexing task
            indexing_task = asyncio.create_task(
                self.stream_indexing_progress(connection_id, indexing_request)
            )
            self.connection_manager.add_task(connection_id, indexing_task)
            
        except ValidationError as e:
            await self.connection_manager.send_message(
                connection_id, MessageType.ERROR,
                {'error': f'Invalid indexing request: {str(e)}'}
            )
    
    async def stream_indexing_progress(self, connection_id: str, indexing_request: IndexingRequest):
        """Stream indexing progress to client."""
        try:
            # Send indexing started message
            await self.connection_manager.send_message(
                connection_id, MessageType.INDEXING_PROGRESS,
                {
                    'status': 'started',
                    'query': indexing_request.query,
                    'stage': 'Initializing indexing process...',
                    'progress': 0
                }
            )
            
            # Convert sources
            sources = None
            if indexing_request.sources:
                sources = []
                for source_str in indexing_request.sources:
                    try:
                        sources.append(DataSource(source_str.lower()))
                    except ValueError:
                        await self.connection_manager.send_message(
                            connection_id, MessageType.ERROR,
                            {'error': f'Invalid source: {source_str}'}
                        )
                        return
            
            # Step 1: Search for data
            await self.connection_manager.send_message(
                connection_id, MessageType.INDEXING_PROGRESS,
                {
                    'status': 'searching',
                    'stage': 'Searching for legal data...',
                    'progress': 10
                }
            )
            
            cases = await self.api_client.search_cases(
                query=indexing_request.query,
                sources=sources,
                limit=indexing_request.limit
            )
            
            # Step 2: Process data
            await self.connection_manager.send_message(
                connection_id, MessageType.INDEXING_PROGRESS,
                {
                    'status': 'processing',
                    'stage': f'Processing {len(cases)} documents...',
                    'progress': 30,
                    'documents_found': len(cases)
                }
            )
            
            processed_docs = await self.processor.process_legal_cases(cases)
            
            # Step 3: Index data with progress updates
            await self.connection_manager.send_message(
                connection_id, MessageType.INDEXING_PROGRESS,
                {
                    'status': 'indexing',
                    'stage': 'Indexing into GraphRAG...',
                    'progress': 60,
                    'documents_processed': len(processed_docs)
                }
            )
            
            # Index documents in batches with progress updates
            batch_size = indexing_request.batch_size
            total_batches = (len(processed_docs) + batch_size - 1) // batch_size
            
            all_results = []
            for batch_index in range(total_batches):
                start_idx = batch_index * batch_size
                end_idx = min((batch_index + 1) * batch_size, len(processed_docs))
                batch = processed_docs[start_idx:end_idx]
                
                batch_results = await self.indexer.index_processed_documents(
                    batch, batch_size=batch_size
                )
                all_results.extend(batch_results)
                
                # Send progress update
                progress = 60 + (30 * (batch_index + 1) / total_batches)
                await self.connection_manager.send_message(
                    connection_id, MessageType.INDEXING_PROGRESS,
                    {
                        'status': 'indexing',
                        'stage': f'Indexed batch {batch_index + 1}/{total_batches}',
                        'progress': int(progress),
                        'batch_results': [
                            {
                                'document_id': r.document_id,
                                'status': r.status.value,
                                'nodes_created': r.nodes_created,
                                'relationships_created': r.relationships_created
                            } for r in batch_results
                        ]
                    }
                )
            
            # Step 4: Complete
            indexing_stats = self.indexer.get_indexing_stats()
            
            await self.connection_manager.send_message(
                connection_id, MessageType.INDEXING_COMPLETE,
                {
                    'status': 'completed',
                    'query': indexing_request.query,
                    'total_documents': len(processed_docs),
                    'successful_documents': indexing_stats.successful_documents,
                    'failed_documents': indexing_stats.failed_documents,
                    'success_rate': indexing_stats.success_rate,
                    'total_nodes_created': indexing_stats.total_nodes_created,
                    'total_relationships_created': indexing_stats.total_relationships_created,
                    'total_processing_time_ms': indexing_stats.total_processing_time_ms,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error in indexing process: {e}")
            await self.connection_manager.send_message(
                connection_id, MessageType.ERROR,
                {'error': f'Indexing failed: {str(e)}'}
            )
    
    async def handle_stop_indexing(self, connection_id: str):
        """Handle request to stop ongoing indexing."""
        # Cancel active tasks for this connection
        if connection_id in self.connection_manager.active_tasks:
            for task in self.connection_manager.active_tasks[connection_id]:
                if not task.done():
                    task.cancel()
            
            await self.connection_manager.send_message(
                connection_id, MessageType.STATUS,
                {'status': 'indexing_stopped', 'message': 'Indexing tasks cancelled'}
            )
    
    async def handle_join_session(self, connection_id: str, data: Dict[str, Any]):
        """Handle request to join collaborative session."""
        try:
            join_request = SessionJoinRequest(**data)
            
            await self.connection_manager.join_session(
                connection_id,
                join_request.session_id,
                join_request.user_id,
                join_request.user_name
            )
            
            await self.connection_manager.send_message(
                connection_id, MessageType.STATUS,
                {
                    'status': 'session_joined',
                    'session_id': join_request.session_id,
                    'user_id': join_request.user_id
                }
            )
            
        except ValidationError as e:
            await self.connection_manager.send_message(
                connection_id, MessageType.ERROR,
                {'error': f'Invalid session join request: {str(e)}'}
            )
    
    async def handle_leave_session(self, connection_id: str):
        """Handle request to leave current session."""
        metadata = self.connection_manager.connection_metadata.get(connection_id, {})
        session_id = metadata.get('session_id')
        
        if session_id:
            # Remove from session
            if session_id in self.connection_manager.sessions:
                self.connection_manager.sessions[session_id].discard(connection_id)
                
                # Notify other session members
                await self.connection_manager.broadcast_to_session(
                    session_id, MessageType.SESSION_UPDATE,
                    {
                        'action': 'user_left',
                        'user_id': metadata.get('user_id'),
                        'connection_id': connection_id
                    }
                )
            
            # Update metadata
            self.connection_manager.connection_metadata[connection_id]['session_id'] = None
            
            await self.connection_manager.send_message(
                connection_id, MessageType.STATUS,
                {'status': 'session_left', 'session_id': session_id}
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket server statistics."""
        return {
            'active_connections': self.connection_manager.get_connection_count(),
            'active_sessions': self.connection_manager.get_session_count(),
            'indexing_stats': self.indexer.get_indexing_stats().__dict__,
            'processing_stats': self.processor.get_processing_stats().__dict__
        }


# Global WebSocket handler instance
websocket_handler = LegalDataWebSocketHandler()


# FastAPI WebSocket endpoint
async def websocket_endpoint(websocket: WebSocket, connection_id: str):
    """Main WebSocket endpoint for legal data operations."""
    await websocket_handler.handle_connection(websocket, connection_id)


# Utility functions for WebSocket management
async def broadcast_system_update(message: str, data: Optional[Dict[str, Any]] = None):
    """Broadcast system update to all connected clients."""
    if data is None:
        data = {}
    
    data.update({
        'message': message,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })
    
    # This would broadcast to all connections
    # Implementation would depend on how you want to handle system-wide broadcasts
    pass


async def get_websocket_stats() -> Dict[str, Any]:
    """Get WebSocket server statistics."""
    return websocket_handler.get_stats()


# Example usage and testing
async def test_websocket_message_handling():
    """Test WebSocket message handling (for development)."""
    
    # Simulate search request
    search_msg = {
        'type': MessageType.SEARCH_REQUEST.value,
        'data': {
            'query': 'patent infringement software',
            'sources': ['courtlistener', 'cap'],
            'limit': 10,
            'stream_results': True
        }
    }
    
    # Simulate indexing request
    indexing_msg = {
        'type': MessageType.START_INDEXING.value,
        'data': {
            'query': 'artificial intelligence patents',
            'sources': ['courtlistener'],
            'limit': 50,
            'batch_size': 10
        }
    }
    
    # Simulate session join
    session_msg = {
        'type': MessageType.JOIN_SESSION.value,
        'data': {
            'session_id': 'test_session_001',
            'user_id': 'test_user',
            'user_name': 'Test User'
        }
    }
    
    print("WebSocket message examples:")
    print("Search request:", json.dumps(search_msg, indent=2))
    print("\nIndexing request:", json.dumps(indexing_msg, indent=2))
    print("\nSession join:", json.dumps(session_msg, indent=2))


if __name__ == "__main__":
    asyncio.run(test_websocket_message_handling())