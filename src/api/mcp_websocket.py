"""
MCP WebSocket API Endpoint
Production-ready WebSocket endpoint for real-time MCP communication.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional, List
import json
import asyncio
from datetime import datetime
import uuid
from enum import Enum

import structlog
from pydantic import BaseModel, Field, ValidationError

from ..services.mcp_sdk_bridge import get_mcp_bridge, MCPServerType
from ..services.mcp_session_manager import get_session_manager, MCPSession
from ..core.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/mcp")


class WSMessageType(str, Enum):
    """WebSocket message types."""
    # Connection management
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    PING = "ping"
    PONG = "pong"
    
    # MCP operations
    TOOL_CALL = "tool_call"
    TOOL_RESPONSE = "tool_response"
    TOOL_LIST = "tool_list"
    
    # Session management
    SESSION_CREATE = "session_create"
    SESSION_DESTROY = "session_destroy"
    SESSION_STATUS = "session_status"
    
    # Case extraction
    EXTRACT_CHAT = "extract_chat"
    EXTRACT_FILE = "extract_file"
    EXTRACT_VALIDATE = "extract_validate"
    
    # Legal consultation
    CONSULT_INIT = "consult_init"
    CONSULT_MESSAGE = "consult_message"
    CONSULT_OPPONENT = "consult_opponent"
    
    # System
    ERROR = "error"
    STATUS = "status"
    STREAM = "stream"


class WSMessage(BaseModel):
    """WebSocket message model."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: WSMessageType
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    session_id: Optional[str] = None


class WebSocketConnection:
    """Manages a single WebSocket connection."""
    
    def __init__(self, websocket: WebSocket, client_id: str):
        self.websocket = websocket
        self.client_id = client_id
        self.session_id: Optional[str] = None
        self.connected_at = datetime.now()
        self.last_ping = datetime.now()
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.tasks: List[asyncio.Task] = []
        
    async def send_message(self, message: WSMessage):
        """Send a message to the client."""
        try:
            await self.websocket.send_json(message.model_dump(mode="json"))
        except Exception as e:
            logger.error(f"Error sending message to {self.client_id}: {e}")
            raise
            
    async def receive_message(self) -> WSMessage:
        """Receive a message from the client."""
        try:
            data = await self.websocket.receive_json()
            return WSMessage(**data)
        except ValidationError as e:
            logger.warning(f"Invalid message from {self.client_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error receiving message from {self.client_id}: {e}")
            raise
            
    def cleanup(self):
        """Clean up connection resources."""
        for task in self.tasks:
            if not task.done():
                task.cancel()


class MCPWebSocketHandler:
    """Handles MCP WebSocket connections."""
    
    def __init__(self):
        self.connections: Dict[str, WebSocketConnection] = {}
        self.bridge = get_mcp_bridge()
        self.session_manager = get_session_manager()
        
    async def handle_connection(self, websocket: WebSocket, client_id: Optional[str] = None):
        """Handle a WebSocket connection."""
        if not client_id:
            client_id = str(uuid.uuid4())
            
        # Accept connection
        await websocket.accept()
        
        # Create connection object
        connection = WebSocketConnection(websocket, client_id)
        self.connections[client_id] = connection
        
        logger.info(f"WebSocket connected: {client_id}")
        
        # Send welcome message
        await connection.send_message(WSMessage(
            type=WSMessageType.CONNECT,
            data={"client_id": client_id, "status": "connected"}
        ))
        
        # Start ping task
        ping_task = asyncio.create_task(self._ping_loop(connection))
        connection.tasks.append(ping_task)
        
        try:
            # Handle messages
            await self._handle_messages(connection)
            
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {client_id}")
        except Exception as e:
            logger.error(f"WebSocket error for {client_id}: {e}")
            await connection.send_message(WSMessage(
                type=WSMessageType.ERROR,
                data={"error": str(e)}
            ))
        finally:
            # Clean up
            connection.cleanup()
            
            # Clean up session if exists
            if connection.session_id:
                await self.session_manager.destroy_session(connection.session_id)
                
            # Remove connection
            self.connections.pop(client_id, None)
            
    async def _handle_messages(self, connection: WebSocketConnection):
        """Handle incoming messages."""
        while True:
            try:
                message = await connection.receive_message()
                
                # Update last activity
                connection.last_ping = datetime.now()
                
                # Route message
                await self._route_message(connection, message)
                
            except ValidationError as e:
                await connection.send_message(WSMessage(
                    type=WSMessageType.ERROR,
                    data={"error": f"Invalid message: {e}"}
                ))
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error handling message: {e}")
                await connection.send_message(WSMessage(
                    type=WSMessageType.ERROR,
                    data={"error": str(e)}
                ))
                
    async def _route_message(self, connection: WebSocketConnection, message: WSMessage):
        """Route message to appropriate handler."""
        handlers = {
            WSMessageType.PING: self._handle_ping,
            WSMessageType.SESSION_CREATE: self._handle_session_create,
            WSMessageType.SESSION_DESTROY: self._handle_session_destroy,
            WSMessageType.SESSION_STATUS: self._handle_session_status,
            WSMessageType.TOOL_CALL: self._handle_tool_call,
            WSMessageType.TOOL_LIST: self._handle_tool_list,
            WSMessageType.EXTRACT_CHAT: self._handle_extract_chat,
            WSMessageType.EXTRACT_FILE: self._handle_extract_file,
            WSMessageType.EXTRACT_VALIDATE: self._handle_extract_validate,
            WSMessageType.CONSULT_INIT: self._handle_consult_init,
            WSMessageType.CONSULT_MESSAGE: self._handle_consult_message,
            WSMessageType.CONSULT_OPPONENT: self._handle_consult_opponent,
        }
        
        handler = handlers.get(message.type)
        if handler:
            await handler(connection, message)
        else:
            await connection.send_message(WSMessage(
                type=WSMessageType.ERROR,
                data={"error": f"Unknown message type: {message.type}"}
            ))
            
    async def _handle_ping(self, connection: WebSocketConnection, message: WSMessage):
        """Handle ping message."""
        await connection.send_message(WSMessage(
            type=WSMessageType.PONG,
            data={"timestamp": datetime.now().isoformat()}
        ))
        
    async def _handle_session_create(self, connection: WebSocketConnection, message: WSMessage):
        """Handle session creation."""
        try:
            # Create session
            session = await self.session_manager.create_session(
                client_id=connection.client_id,
                metadata=message.data or {}
            )
            
            connection.session_id = session.session_id
            
            await connection.send_message(WSMessage(
                type=WSMessageType.SESSION_CREATE,
                data={
                    "session_id": session.session_id,
                    "status": "created"
                }
            ))
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            await connection.send_message(WSMessage(
                type=WSMessageType.ERROR,
                data={"error": f"Failed to create session: {e}"}
            ))
            
    async def _handle_session_destroy(self, connection: WebSocketConnection, message: WSMessage):
        """Handle session destruction."""
        if connection.session_id:
            await self.session_manager.destroy_session(connection.session_id)
            connection.session_id = None
            
        await connection.send_message(WSMessage(
            type=WSMessageType.SESSION_DESTROY,
            data={"status": "destroyed"}
        ))
        
    async def _handle_session_status(self, connection: WebSocketConnection, message: WSMessage):
        """Handle session status request."""
        if connection.session_id:
            session = await self.session_manager.get_session(connection.session_id)
            if session:
                await connection.send_message(WSMessage(
                    type=WSMessageType.SESSION_STATUS,
                    data=session.to_dict()
                ))
            else:
                await connection.send_message(WSMessage(
                    type=WSMessageType.ERROR,
                    data={"error": "Session not found"}
                ))
        else:
            await connection.send_message(WSMessage(
                type=WSMessageType.ERROR,
                data={"error": "No active session"}
            ))
            
    async def _handle_tool_call(self, connection: WebSocketConnection, message: WSMessage):
        """Handle tool call."""
        try:
            data = message.data or {}
            server_name = data.get("server")
            tool_name = data.get("tool")
            arguments = data.get("arguments", {})
            
            if not server_name or not tool_name:
                raise ValueError("Missing server or tool name")
                
            # Call tool
            result = await self.bridge.call_tool(server_name, tool_name, arguments)
            
            await connection.send_message(WSMessage(
                type=WSMessageType.TOOL_RESPONSE,
                data={
                    "server": server_name,
                    "tool": tool_name,
                    "result": result
                }
            ))
            
        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            await connection.send_message(WSMessage(
                type=WSMessageType.ERROR,
                data={"error": f"Tool call failed: {e}"}
            ))
            
    async def _handle_tool_list(self, connection: WebSocketConnection, message: WSMessage):
        """Handle tool list request."""
        try:
            server_name = message.data.get("server") if message.data else None
            
            if not server_name:
                raise ValueError("Missing server name")
                
            # List tools
            tools = await self.bridge.list_tools(server_name)
            
            await connection.send_message(WSMessage(
                type=WSMessageType.TOOL_LIST,
                data={
                    "server": server_name,
                    "tools": tools
                }
            ))
            
        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            await connection.send_message(WSMessage(
                type=WSMessageType.ERROR,
                data={"error": f"Failed to list tools: {e}"}
            ))
            
    async def _handle_extract_chat(self, connection: WebSocketConnection, message: WSMessage):
        """Handle chat-based case extraction."""
        try:
            data = message.data or {}
            user_input = data.get("input", "")
            context = data.get("context", {})
            
            # Stream responses
            async def stream_callback(chunk: str):
                await connection.send_message(WSMessage(
                    type=WSMessageType.STREAM,
                    data={"content": chunk}
                ))
                
            # Call case extractor
            result = await self.bridge.call_tool(
                "case_extractor",
                "chat_extract",
                {
                    "input": user_input,
                    "context": context,
                    "stream": True,
                    "stream_callback": stream_callback
                }
            )
            
            await connection.send_message(WSMessage(
                type=WSMessageType.EXTRACT_CHAT,
                data={"result": result}
            ))
            
        except Exception as e:
            logger.error(f"Chat extraction failed: {e}")
            await connection.send_message(WSMessage(
                type=WSMessageType.ERROR,
                data={"error": f"Chat extraction failed: {e}"}
            ))
            
    async def _handle_extract_file(self, connection: WebSocketConnection, message: WSMessage):
        """Handle file-based case extraction."""
        try:
            data = message.data or {}
            file_path = data.get("file_path")
            file_content = data.get("file_content")
            file_type = data.get("file_type", "auto")
            
            if not file_path and not file_content:
                raise ValueError("Either file_path or file_content must be provided")
                
            # Call file extractor
            result = await self.bridge.call_tool(
                "case_extractor",
                "extract_from_file",
                {
                    "file_path": file_path,
                    "file_content": file_content,
                    "file_type": file_type
                }
            )
            
            await connection.send_message(WSMessage(
                type=WSMessageType.EXTRACT_FILE,
                data={"result": result}
            ))
            
        except Exception as e:
            logger.error(f"File extraction failed: {e}")
            await connection.send_message(WSMessage(
                type=WSMessageType.ERROR,
                data={"error": f"File extraction failed: {e}"}
            ))
            
    async def _handle_extract_validate(self, connection: WebSocketConnection, message: WSMessage):
        """Handle extraction validation."""
        try:
            data = message.data or {}
            extracted_data = data.get("extracted_data", {})
            
            # Validate extraction
            result = await self.bridge.call_tool(
                "case_extractor",
                "validate_extraction",
                {"data": extracted_data}
            )
            
            await connection.send_message(WSMessage(
                type=WSMessageType.EXTRACT_VALIDATE,
                data={"result": result}
            ))
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            await connection.send_message(WSMessage(
                type=WSMessageType.ERROR,
                data={"error": f"Validation failed: {e}"}
            ))
            
    async def _handle_consult_init(self, connection: WebSocketConnection, message: WSMessage):
        """Handle consultation initialization."""
        try:
            data = message.data or {}
            case_data = data.get("case_data", {})
            
            # Initialize consultation
            result = await self.bridge.call_tool(
                "lawyer_server",
                "init_consultation",
                {"case_data": case_data}
            )
            
            # Store consultation ID in session
            if connection.session_id:
                session = await self.session_manager.get_session(connection.session_id)
                if session:
                    session.metadata["consultation_id"] = result.get("consultation_id")
                    await self.session_manager.update_session(session)
                    
            await connection.send_message(WSMessage(
                type=WSMessageType.CONSULT_INIT,
                data={"result": result}
            ))
            
        except Exception as e:
            logger.error(f"Consultation init failed: {e}")
            await connection.send_message(WSMessage(
                type=WSMessageType.ERROR,
                data={"error": f"Consultation init failed: {e}"}
            ))
            
    async def _handle_consult_message(self, connection: WebSocketConnection, message: WSMessage):
        """Handle consultation message."""
        try:
            data = message.data or {}
            user_message = data.get("message", "")
            consultation_id = data.get("consultation_id")
            
            # Get consultation ID from session if not provided
            if not consultation_id and connection.session_id:
                session = await self.session_manager.get_session(connection.session_id)
                if session:
                    consultation_id = session.metadata.get("consultation_id")
                    
            if not consultation_id:
                raise ValueError("No active consultation")
                
            # Stream responses
            async def stream_callback(chunk: str):
                await connection.send_message(WSMessage(
                    type=WSMessageType.STREAM,
                    data={"content": chunk}
                ))
                
            # Send message
            result = await self.bridge.call_tool(
                "lawyer_server",
                "send_message",
                {
                    "consultation_id": consultation_id,
                    "message": user_message,
                    "stream": True,
                    "stream_callback": stream_callback
                }
            )
            
            await connection.send_message(WSMessage(
                type=WSMessageType.CONSULT_MESSAGE,
                data={"result": result}
            ))
            
        except Exception as e:
            logger.error(f"Consultation message failed: {e}")
            await connection.send_message(WSMessage(
                type=WSMessageType.ERROR,
                data={"error": f"Consultation message failed: {e}"}
            ))
            
    async def _handle_consult_opponent(self, connection: WebSocketConnection, message: WSMessage):
        """Handle opponent simulation."""
        try:
            data = message.data or {}
            consultation_id = data.get("consultation_id")
            scenario = data.get("scenario", {})
            
            # Get consultation ID from session if not provided
            if not consultation_id and connection.session_id:
                session = await self.session_manager.get_session(connection.session_id)
                if session:
                    consultation_id = session.metadata.get("consultation_id")
                    
            if not consultation_id:
                raise ValueError("No active consultation")
                
            # Simulate opponent
            result = await self.bridge.call_tool(
                "lawyer_server",
                "simulate_opponent",
                {
                    "consultation_id": consultation_id,
                    "scenario": scenario
                }
            )
            
            await connection.send_message(WSMessage(
                type=WSMessageType.CONSULT_OPPONENT,
                data={"result": result}
            ))
            
        except Exception as e:
            logger.error(f"Opponent simulation failed: {e}")
            await connection.send_message(WSMessage(
                type=WSMessageType.ERROR,
                data={"error": f"Opponent simulation failed: {e}"}
            ))
            
    async def _ping_loop(self, connection: WebSocketConnection):
        """Send periodic pings to keep connection alive."""
        while True:
            try:
                await asyncio.sleep(30)  # Ping every 30 seconds
                
                # Check if connection is stale
                if (datetime.now() - connection.last_ping).seconds > 60:
                    logger.warning(f"Connection {connection.client_id} is stale")
                    break
                    
                # Send ping
                await connection.send_message(WSMessage(
                    type=WSMessageType.PING,
                    data={"timestamp": datetime.now().isoformat()}
                ))
                
            except Exception as e:
                logger.error(f"Ping failed for {connection.client_id}: {e}")
                break


# Create handler instance
handler = MCPWebSocketHandler()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None, description="Optional client ID")
):
    """WebSocket endpoint for MCP communication."""
    await handler.handle_connection(websocket, client_id)


@router.get("/status")
async def get_mcp_status():
    """Get MCP system status."""
    bridge = get_mcp_bridge()
    session_manager = get_session_manager()
    
    return JSONResponse({
        "bridge": bridge.get_status(),
        "sessions": session_manager.get_status(),
        "connections": len(handler.connections)
    })


@router.get("/connections")
async def get_connections():
    """Get active WebSocket connections."""
    return JSONResponse({
        "connections": [
            {
                "client_id": conn.client_id,
                "session_id": conn.session_id,
                "connected_at": conn.connected_at.isoformat(),
                "last_ping": conn.last_ping.isoformat()
            }
            for conn in handler.connections.values()
        ]
    })