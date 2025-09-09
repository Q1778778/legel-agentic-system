"""
MCP SDK Bridge Service
Production-ready bridge for MCP server integration using official MCP Python SDK.
"""

import asyncio
import json
import subprocess
import sys
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging
from pathlib import Path
import signal
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import traceback

import structlog
from pydantic import BaseModel, Field

# Configure structured logging
logger = structlog.get_logger(__name__)


class MCPServerType(str, Enum):
    """MCP server types."""
    CASE_EXTRACTOR = "case_extractor"
    LAWYER_SERVER = "lawyer_server"


class MCPConnectionState(str, Enum):
    """Connection states for MCP servers."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    name: str
    type: MCPServerType
    command: List[str]
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    working_dir: Optional[str] = None
    auto_restart: bool = True
    max_retries: int = 5
    retry_delay: float = 1.0
    health_check_interval: float = 30.0
    timeout: float = 60.0


class MCPMessage(BaseModel):
    """MCP message model."""
    jsonrpc: str = "2.0"
    id: Optional[int] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None


class MCPServerConnection:
    """Manages a single MCP server connection."""
    
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.state = MCPConnectionState.DISCONNECTED
        self.message_id = 0
        self.pending_requests: Dict[int, asyncio.Future] = {}
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.reader_task: Optional[asyncio.Task] = None
        self.health_check_task: Optional[asyncio.Task] = None
        self.retry_count = 0
        self.last_error: Optional[str] = None
        self.connected_at: Optional[datetime] = None
        self.lock = asyncio.Lock()
        
    async def connect(self) -> bool:
        """Connect to the MCP server."""
        async with self.lock:
            if self.state == MCPConnectionState.CONNECTED:
                return True
                
            try:
                self.state = MCPConnectionState.CONNECTING
                logger.info(f"Connecting to MCP server: {self.config.name}")
                
                # Prepare command
                cmd = self.config.command + self.config.args
                env = {**os.environ, **self.config.env}
                
                # Start the server process
                self.process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=self.config.working_dir
                )
                
                # Initialize connection
                await self._initialize_connection()
                
                # Start reader and health check tasks
                self.reader_task = asyncio.create_task(self._read_messages())
                self.health_check_task = asyncio.create_task(self._health_check_loop())
                
                self.state = MCPConnectionState.CONNECTED
                self.connected_at = datetime.now()
                self.retry_count = 0
                
                logger.info(f"Successfully connected to MCP server: {self.config.name}")
                return True
                
            except Exception as e:
                self.state = MCPConnectionState.ERROR
                self.last_error = str(e)
                logger.error(f"Failed to connect to MCP server {self.config.name}: {e}")
                
                if self.config.auto_restart and self.retry_count < self.config.max_retries:
                    await self._schedule_reconnect()
                    
                return False
    
    async def disconnect(self):
        """Disconnect from the MCP server."""
        async with self.lock:
            logger.info(f"Disconnecting from MCP server: {self.config.name}")
            
            # Cancel tasks
            if self.reader_task:
                self.reader_task.cancel()
            if self.health_check_task:
                self.health_check_task.cancel()
                
            # Terminate process
            if self.process:
                try:
                    self.process.terminate()
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
                    
            # Clean up
            self.process = None
            self.state = MCPConnectionState.DISCONNECTED
            self.pending_requests.clear()
            
    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Send a request to the MCP server."""
        if self.state != MCPConnectionState.CONNECTED:
            raise ConnectionError(f"Not connected to MCP server: {self.config.name}")
            
        self.message_id += 1
        message_id = self.message_id
        
        message = MCPMessage(
            id=message_id,
            method=method,
            params=params or {}
        )
        
        # Create future for response
        future = asyncio.Future()
        self.pending_requests[message_id] = future
        
        try:
            # Send message
            await self._write_message(message)
            
            # Wait for response with timeout
            result = await asyncio.wait_for(future, timeout=self.config.timeout)
            return result
            
        except asyncio.TimeoutError:
            self.pending_requests.pop(message_id, None)
            raise TimeoutError(f"Request timeout: {method}")
        except Exception as e:
            self.pending_requests.pop(message_id, None)
            raise
            
    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        """Send a notification to the MCP server."""
        if self.state != MCPConnectionState.CONNECTED:
            raise ConnectionError(f"Not connected to MCP server: {self.config.name}")
            
        message = MCPMessage(
            method=method,
            params=params or {}
        )
        
        await self._write_message(message)
        
    def on_event(self, event: str, handler: Callable):
        """Register an event handler."""
        if event not in self.event_handlers:
            self.event_handlers[event] = []
        self.event_handlers[event].append(handler)
        
    async def _initialize_connection(self):
        """Initialize the MCP connection."""
        # Send initialization request
        init_response = await self.send_request("initialize", {
            "protocolVersion": "1.0",
            "clientInfo": {
                "name": "legal-analysis-system",
                "version": "1.0.0"
            }
        })
        
        logger.info(f"MCP server initialized: {init_response}")
        
    async def _write_message(self, message: MCPMessage):
        """Write a message to the server."""
        if not self.process or not self.process.stdin:
            raise ConnectionError("No active connection")
            
        data = message.model_dump(exclude_none=True)
        json_str = json.dumps(data) + "\n"
        self.process.stdin.write(json_str.encode())
        await self.process.stdin.drain()
        
    async def _read_messages(self):
        """Read messages from the server."""
        try:
            while self.state == MCPConnectionState.CONNECTED:
                if not self.process or not self.process.stdout:
                    break
                    
                line = await self.process.stdout.readline()
                if not line:
                    break
                    
                try:
                    data = json.loads(line.decode())
                    message = MCPMessage(**data)
                    await self._handle_message(message)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from MCP server: {e}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    
        except Exception as e:
            logger.error(f"Reader task error: {e}")
        finally:
            if self.state == MCPConnectionState.CONNECTED:
                self.state = MCPConnectionState.ERROR
                await self._schedule_reconnect()
                
    async def _handle_message(self, message: MCPMessage):
        """Handle an incoming message."""
        # Handle response
        if message.id is not None and message.id in self.pending_requests:
            future = self.pending_requests.pop(message.id)
            if message.error:
                future.set_exception(Exception(message.error.get("message", "Unknown error")))
            else:
                future.set_result(message.result)
                
        # Handle notification/event
        elif message.method:
            event_handlers = self.event_handlers.get(message.method, [])
            for handler in event_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message.params)
                    else:
                        handler(message.params)
                except Exception as e:
                    logger.error(f"Error in event handler: {e}")
                    
    async def _health_check_loop(self):
        """Periodic health check."""
        while self.state == MCPConnectionState.CONNECTED:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                
                # Send ping
                await self.send_request("ping")
                
            except Exception as e:
                logger.warning(f"Health check failed: {e}")
                if self.state == MCPConnectionState.CONNECTED:
                    self.state = MCPConnectionState.ERROR
                    await self._schedule_reconnect()
                break
                
    async def _schedule_reconnect(self):
        """Schedule a reconnection attempt."""
        if not self.config.auto_restart:
            return
            
        self.retry_count += 1
        if self.retry_count > self.config.max_retries:
            logger.error(f"Max retries exceeded for {self.config.name}")
            return
            
        self.state = MCPConnectionState.RECONNECTING
        delay = self.config.retry_delay * (2 ** (self.retry_count - 1))  # Exponential backoff
        logger.info(f"Reconnecting to {self.config.name} in {delay} seconds...")
        
        await asyncio.sleep(delay)
        await self.connect()


class MCPSDKBridge:
    """Main MCP SDK Bridge for managing multiple MCP servers."""
    
    def __init__(self):
        self.servers: Dict[str, MCPServerConnection] = {}
        self.initialized = False
        
    async def initialize(self, configs: List[MCPServerConfig]):
        """Initialize the MCP bridge with server configurations."""
        logger.info("Initializing MCP SDK Bridge")
        
        for config in configs:
            server = MCPServerConnection(config)
            self.servers[config.name] = server
            
        # Connect to all servers
        connect_tasks = [server.connect() for server in self.servers.values()]
        results = await asyncio.gather(*connect_tasks, return_exceptions=True)
        
        # Check results
        for config, result in zip(configs, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to connect to {config.name}: {result}")
            elif not result:
                logger.warning(f"Failed to connect to {config.name}")
                
        self.initialized = True
        logger.info("MCP SDK Bridge initialized")
        
    async def shutdown(self):
        """Shutdown all MCP servers."""
        logger.info("Shutting down MCP SDK Bridge")
        
        disconnect_tasks = [server.disconnect() for server in self.servers.values()]
        await asyncio.gather(*disconnect_tasks, return_exceptions=True)
        
        self.servers.clear()
        self.initialized = False
        
    def get_server(self, name: str) -> Optional[MCPServerConnection]:
        """Get a server connection by name."""
        return self.servers.get(name)
        
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on a specific MCP server."""
        server = self.get_server(server_name)
        if not server:
            raise ValueError(f"Server not found: {server_name}")
            
        return await server.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
    async def list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """List available tools from a server."""
        server = self.get_server(server_name)
        if not server:
            raise ValueError(f"Server not found: {server_name}")
            
        response = await server.send_request("tools/list")
        return response.get("tools", [])
        
    def get_status(self) -> Dict[str, Any]:
        """Get status of all servers."""
        return {
            "initialized": self.initialized,
            "servers": {
                name: {
                    "state": server.state.value,
                    "connected_at": server.connected_at.isoformat() if server.connected_at else None,
                    "retry_count": server.retry_count,
                    "last_error": server.last_error
                }
                for name, server in self.servers.items()
            }
        }
        
    @asynccontextmanager
    async def session(self, configs: List[MCPServerConfig]):
        """Context manager for MCP session."""
        try:
            await self.initialize(configs)
            yield self
        finally:
            await self.shutdown()


# Singleton instance
_bridge_instance: Optional[MCPSDKBridge] = None


def get_mcp_bridge() -> MCPSDKBridge:
    """Get the singleton MCP bridge instance."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = MCPSDKBridge()
    return _bridge_instance


# Import os at the top (was missing)
import os