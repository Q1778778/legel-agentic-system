"""
WebSocket endpoints for real-time workflow updates
"""
from typing import Dict, Any, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import json
import asyncio
import logging
from datetime import datetime

from ..services.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["websocket"])

# Connection manager for WebSocket connections
class ConnectionManager:
    """Manages WebSocket connections for workflows"""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.connection_metadata: Dict[WebSocket, Dict[str, Any]] = {}
    
    async def connect(self, websocket: WebSocket, workflow_id: str):
        """
        Accept and register a new WebSocket connection
        
        Args:
            websocket: WebSocket connection
            workflow_id: Workflow ID to subscribe to
        """
        await websocket.accept()
        
        if workflow_id not in self.active_connections:
            self.active_connections[workflow_id] = set()
        
        self.active_connections[workflow_id].add(websocket)
        self.connection_metadata[websocket] = {
            "workflow_id": workflow_id,
            "connected_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"WebSocket connected for workflow {workflow_id}")
        
        # Send initial connection message
        await self.send_personal_message(
            {
                "type": "connection_established",
                "workflow_id": workflow_id,
                "timestamp": datetime.utcnow().isoformat()
            },
            websocket
        )
    
    def disconnect(self, websocket: WebSocket):
        """
        Remove a WebSocket connection
        
        Args:
            websocket: WebSocket connection to remove
        """
        metadata = self.connection_metadata.get(websocket)
        if metadata:
            workflow_id = metadata["workflow_id"]
            if workflow_id in self.active_connections:
                self.active_connections[workflow_id].discard(websocket)
                if not self.active_connections[workflow_id]:
                    del self.active_connections[workflow_id]
            
            del self.connection_metadata[websocket]
            logger.info(f"WebSocket disconnected for workflow {workflow_id}")
    
    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        """
        Send a message to a specific WebSocket connection
        
        Args:
            message: Message to send
            websocket: Target WebSocket connection
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending message to WebSocket: {e}")
    
    async def broadcast_to_workflow(self, workflow_id: str, message: Dict[str, Any]):
        """
        Broadcast a message to all connections for a workflow
        
        Args:
            workflow_id: Workflow ID
            message: Message to broadcast
        """
        connections = self.active_connections.get(workflow_id, set())
        if connections:
            # Add timestamp if not present
            if "timestamp" not in message:
                message["timestamp"] = datetime.utcnow().isoformat()
            
            # Send to all connections
            disconnected = []
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to connection: {e}")
                    disconnected.append(connection)
            
            # Clean up disconnected connections
            for connection in disconnected:
                self.disconnect(connection)


# Global connection manager
manager = ConnectionManager()


def create_workflow_callback(workflow_id: str):
    """
    Create a callback function for workflow updates
    
    Args:
        workflow_id: Workflow ID
        
    Returns:
        Callback function for workflow updates
    """
    async def callback(update_type: str, data: Any):
        """
        Callback for workflow updates
        
        Args:
            update_type: Type of update
            data: Update data
        """
        # Map update types to WebSocket event types
        if update_type == "workflow_update":
            message = {
                "type": "workflow_update",
                **data
            }
        elif update_type == "argument_generated":
            message = {
                "type": "argument_generated",
                "agent": data.get("agent", "unknown"),
                "content": data.get("content", ""),
                "thinking": data.get("thinking", ""),
                "timestamp": data.get("timestamp", datetime.utcnow().isoformat())
            }
        elif update_type == "feedback_ready":
            message = {
                "type": "feedback_ready",
                "feedback": data.get("feedback", ""),
                "timestamp": datetime.utcnow().isoformat()
            }
        elif update_type == "workflow_error":
            message = {
                "type": "error",
                "error": data.get("error", "Unknown error"),
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            message = {
                "type": update_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Broadcast to all connections for this workflow
        await manager.broadcast_to_workflow(workflow_id, message)
    
    return callback


@router.websocket("/ws/{workflow_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    workflow_id: str,
    token: str = Query(None, description="Optional authentication token")
):
    """
    WebSocket endpoint for workflow updates
    
    Args:
        websocket: WebSocket connection
        workflow_id: Workflow ID to subscribe to
        token: Optional authentication token
    """
    # TODO: Validate token if provided
    if token:
        # Implement token validation here
        pass
    
    await manager.connect(websocket, workflow_id)
    
    # Get workflow engine instance
    from .workflows import workflow_engine
    
    # Register callback for this workflow
    callback = create_workflow_callback(workflow_id)
    workflow_engine.register_update_callback(workflow_id, callback)
    
    try:
        # Check if workflow exists and send current status
        workflow = workflow_engine.get_workflow(workflow_id)
        if workflow:
            await manager.send_personal_message(
                {
                    "type": "workflow_status",
                    "status": workflow.status.value,
                    "current_step": workflow.current_step.value if workflow.current_step else None,
                    "steps_completed": [step.value for step in workflow.steps_completed],
                    "timestamp": datetime.utcnow().isoformat()
                },
                websocket
            )
            
            # If workflow has messages, send them
            if workflow.output_data.get("debate_messages"):
                for message in workflow.output_data["debate_messages"]:
                    await manager.send_personal_message(
                        {
                            "type": "argument_generated",
                            "agent": message.get("agent", "unknown"),
                            "content": message.get("content", ""),
                            "thinking": message.get("thinking", ""),
                            "timestamp": message.get("timestamp", datetime.utcnow().isoformat())
                        },
                        websocket
                    )
                    await asyncio.sleep(0.1)  # Small delay between messages
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_json()
                
                # Handle different message types
                message_type = data.get("type")
                
                if message_type == "ping":
                    # Respond to ping
                    await manager.send_personal_message(
                        {
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        websocket
                    )
                elif message_type == "get_status":
                    # Send current workflow status
                    workflow = workflow_engine.get_workflow(workflow_id)
                    if workflow:
                        await manager.send_personal_message(
                            {
                                "type": "workflow_status",
                                "status": workflow.status.value,
                                "current_step": workflow.current_step.value if workflow.current_step else None,
                                "timestamp": datetime.utcnow().isoformat()
                            },
                            websocket
                        )
                else:
                    # Echo unknown messages back
                    await manager.send_personal_message(
                        {
                            "type": "echo",
                            "original": data,
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        websocket
                    )
                    
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await manager.send_personal_message(
                    {
                        "type": "error",
                        "error": "Invalid JSON format",
                        "timestamp": datetime.utcnow().isoformat()
                    },
                    websocket
                )
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                await manager.send_personal_message(
                    {
                        "type": "error",
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    },
                    websocket
                )
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# Additional endpoint for broadcasting to all workflow connections (admin use)
@router.post("/api/websocket/broadcast/{workflow_id}")
async def broadcast_message(workflow_id: str, message: Dict[str, Any]):
    """
    Broadcast a message to all WebSocket connections for a workflow (admin endpoint)
    
    Args:
        workflow_id: Workflow ID
        message: Message to broadcast
        
    Returns:
        Broadcast status
    """
    connections_count = len(manager.active_connections.get(workflow_id, set()))
    
    if connections_count == 0:
        return {
            "status": "no_connections",
            "workflow_id": workflow_id,
            "connections": 0
        }
    
    await manager.broadcast_to_workflow(workflow_id, message)
    
    return {
        "status": "broadcasted",
        "workflow_id": workflow_id,
        "connections": connections_count
    }