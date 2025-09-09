"""
MCP Bridge Service - Handles communication with stdio-based MCP servers.

This module provides a bridge between HTTP APIs and stdio-based MCP servers,
managing subprocess communication using the MCP (Model Context Protocol).
"""

import asyncio
import json
import logging
import subprocess
import uuid
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class MCPBridgeService:
    """Bridge service for communicating with stdio-based MCP servers."""
    
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.base_path = Path(__file__).parent.parent.parent  # Project root
        
        # MCP server configurations
        self.server_configs = {
            "case_extractor": {
                "path": self.base_path / "mcp_case_extractor" / "server.py",
                "name": "Case Extractor",
                "description": "Extracts legal case information from text and files"
            },
            "lawyer_server": {
                "path": self.base_path / "mcp_lawyer_server" / "server.py", 
                "name": "Lawyer Agent",
                "description": "Provides legal analysis and consultation"
            }
        }
    
    async def initialize_server(self, server_type: str) -> bool:
        """Initialize and start an MCP server process."""
        if server_type not in self.server_configs:
            logger.error(f"Unknown server type: {server_type}")
            return False
            
        config = self.server_configs[server_type]
        server_path = config["path"]
        
        if not server_path.exists():
            logger.error(f"MCP server not found: {server_path}")
            return False
            
        try:
            # Start MCP server process with stdio pipes
            process = subprocess.Popen(
                ["python", str(server_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=server_path.parent
            )
            
            self.processes[server_type] = process
            
            # Send initialization request
            init_request = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "roots": {"listChanged": True},
                        "sampling": {}
                    },
                    "clientInfo": {
                        "name": "legal-agentic-system",
                        "version": "1.0.0"
                    }
                }
            }
            
            await self._send_request(server_type, init_request)
            logger.info(f"Successfully initialized {config['name']} server")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize {server_type}: {str(e)}")
            return False
    
    async def _send_request(self, server_type: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send a JSON-RPC request to an MCP server."""
        process = self.processes.get(server_type)
        if not process:
            logger.error(f"No process found for server type: {server_type}")
            return None
            
        try:
            # Send request
            request_json = json.dumps(request) + "\n"
            process.stdin.write(request_json)
            process.stdin.flush()
            
            # Read response with timeout
            response_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, process.stdout.readline
                ),
                timeout=30.0
            )
            
            if not response_line:
                logger.error(f"Empty response from {server_type}")
                return None
                
            response = json.loads(response_line.strip())
            
            if "error" in response:
                logger.error(f"MCP Error from {server_type}: {response['error']}")
                
            return response
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for response from {server_type}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from {server_type}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error communicating with {server_type}: {e}")
            return None
    
    async def call_tool(self, server_type: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a specific tool on an MCP server."""
        # Ensure server is initialized
        if server_type not in self.processes:
            success = await self.initialize_server(server_type)
            if not success:
                return {"error": f"Failed to initialize {server_type} server"}
        
        request = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        response = await self._send_request(server_type, request)
        
        if not response:
            return {"error": "No response from MCP server"}
            
        if "error" in response:
            return {"error": response["error"]}
            
        return response.get("result", {})
    
    async def list_tools(self, server_type: str) -> List[Dict[str, Any]]:
        """List available tools on an MCP server."""
        if server_type not in self.processes:
            success = await self.initialize_server(server_type)
            if not success:
                return []
        
        request = {
            "jsonrpc": "2.0", 
            "id": str(uuid.uuid4()),
            "method": "tools/list",
            "params": {}
        }
        
        response = await self._send_request(server_type, request)
        
        if not response or "error" in response:
            return []
            
        return response.get("result", {}).get("tools", [])
    
    async def start_chatbox_extraction(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Start a new chatbox extraction session."""
        if not session_id:
            session_id = str(uuid.uuid4())
            
        try:
            result = await self.call_tool(
                "case_extractor",
                "start_chatbox_extraction",
                {"session_id": session_id}
            )
            
            if "error" not in result:
                self.sessions[session_id] = {
                    "type": "chatbox",
                    "created_at": datetime.now().isoformat(),
                    "status": "active"
                }
            
            return {"session_id": session_id, **result}
            
        except Exception as e:
            logger.error(f"Error starting chatbox extraction: {e}")
            return {"error": str(e)}
    
    async def chatbox_respond(self, session_id: str, user_input: str) -> Dict[str, Any]:
        """Send user input to chatbox extraction session."""
        try:
            result = await self.call_tool(
                "case_extractor",
                "chatbox_respond",
                {
                    "session_id": session_id,
                    "user_input": user_input
                }
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in chatbox response: {e}")
            return {"error": str(e)}
    
    async def extract_from_file(self, file_content: str, file_type: str) -> Dict[str, Any]:
        """Extract case information from uploaded file."""
        try:
            result = await self.call_tool(
                "case_extractor",
                "extract_from_document",
                {
                    "content": file_content,
                    "file_type": file_type,
                    "extract_all": True
                }
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error extracting from file: {e}")
            return {"error": str(e)}
    
    async def legal_consultation(self, case_context: Dict[str, Any], query: str) -> Dict[str, Any]:
        """Get legal consultation from lawyer server."""
        try:
            result = await self.call_tool(
                "lawyer_server",
                "legal_consultation",
                {
                    "case_context": case_context,
                    "query": query
                }
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in legal consultation: {e}")
            return {"error": str(e)}
    
    def get_server_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all MCP servers."""
        status = {}
        
        for server_type, config in self.server_configs.items():
            process = self.processes.get(server_type)
            
            if process and process.poll() is None:
                # Process is running
                status[server_type] = {
                    "name": config["name"],
                    "status": "running",
                    "pid": process.pid
                }
            elif config["path"].exists():
                # Server available but not running
                status[server_type] = {
                    "name": config["name"],
                    "status": "available",
                    "path": str(config["path"])
                }
            else:
                # Server not found
                status[server_type] = {
                    "name": config["name"],
                    "status": "not_found",
                    "path": str(config["path"])
                }
        
        return status
    
    async def shutdown_server(self, server_type: str) -> bool:
        """Shutdown a specific MCP server."""
        process = self.processes.get(server_type)
        if not process:
            return True
            
        try:
            # Send shutdown request
            shutdown_request = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "notifications/shutdown",
                "params": {}
            }
            
            await self._send_request(server_type, shutdown_request)
            
            # Wait for process to terminate
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, process.wait),
                timeout=5.0
            )
            
            del self.processes[server_type]
            logger.info(f"Successfully shutdown {server_type} server")
            return True
            
        except asyncio.TimeoutError:
            # Force kill if timeout
            process.kill()
            del self.processes[server_type]
            logger.warning(f"Force killed {server_type} server")
            return True
        except Exception as e:
            logger.error(f"Error shutting down {server_type}: {e}")
            return False
    
    async def shutdown_all(self):
        """Shutdown all MCP servers."""
        for server_type in list(self.processes.keys()):
            await self.shutdown_server(server_type)


# Global bridge service instance
mcp_bridge = MCPBridgeService()