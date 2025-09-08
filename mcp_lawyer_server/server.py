"""MCP Server implementation for conversational lawyer agent system."""

import asyncio
import json
import sys
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog
import yaml
from pathlib import Path
import os
from dotenv import load_dotenv

# MCP imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    ToolResult,
    INTERNAL_ERROR
)

# Local imports
from .conversation_manager import ConversationManager
from .legal_context import CaseInfo, LawyerInfo, PartyRole
from .lawyer_agent import LawyerAgent

# Load environment variables
load_dotenv()

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class MCPLawyerServer:
    """MCP Server for lawyer agent system."""
    
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the MCP server.
        
        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Initialize MCP server
        self.server = Server("lawyer-agent")
        
        # Initialize components
        self.conversation_manager = ConversationManager(
            max_sessions=self.config["session"]["max_sessions"],
            session_ttl=self.config["session"]["session_ttl"],
            max_history_per_session=self.config["session"]["max_history_per_session"],
            cleanup_interval=self.config["session"]["cleanup_interval"]
        )
        
        # Initialize lawyer agent
        self.lawyer_agent = LawyerAgent(
            graphrag_base_url=self.config["graphrag"]["base_url"],
            openai_api_key=os.getenv("OPENAI_API_KEY") or self.config["openai"]["api_key"],
            openai_model=self.config["openai"]["model"],
            config=self.config
        )
        
        # Register tools
        self._register_tools()
        
        # Session tracking
        self.active_sessions: Dict[str, str] = {}  # client_id -> session_id mapping
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file.
        
        Args:
            config_path: Path to config file
            
        Returns:
            Configuration dictionary
        """
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                # Use default config
                logger.warning(f"Config file {config_path} not found, using defaults")
                return self._get_default_config()
                
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
                
            # Replace environment variables
            config = self._replace_env_vars(config)
            
            return config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return self._get_default_config()
            
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration.
        
        Returns:
            Default config dictionary
        """
        return {
            "server": {
                "host": "0.0.0.0",
                "port": 3000,
                "transport": "stdio"
            },
            "graphrag": {
                "base_url": "http://localhost:8000",
                "api_version": "v1"
            },
            "openai": {
                "api_key": os.getenv("OPENAI_API_KEY", ""),
                "model": "gpt-4-turbo-preview",
                "temperature": 0.7,
                "max_tokens": 2000
            },
            "opponent_simulation": {
                "search_strategy": {
                    "opposite_outcome_weight": 0.8,
                    "counter_argument_weight": 0.7,
                    "weakness_identification_weight": 0.6
                },
                "max_precedents": 5,
                "confidence_threshold": 0.65
            },
            "session": {
                "max_sessions": 1000,
                "session_ttl": 3600,
                "max_history_per_session": 100,
                "cleanup_interval": 300
            },
            "features": {
                "opponent_simulation": True,
                "case_analysis": True,
                "precedent_search": True
            }
        }
        
    def _replace_env_vars(self, config: Any) -> Any:
        """Recursively replace environment variables in config.
        
        Args:
            config: Configuration object
            
        Returns:
            Config with env vars replaced
        """
        if isinstance(config, dict):
            return {k: self._replace_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._replace_env_vars(item) for item in config]
        elif isinstance(config, str) and config.startswith("${") and config.endswith("}"):
            env_var = config[2:-1]
            return os.getenv(env_var, config)
        else:
            return config
            
    def _register_tools(self):
        """Register MCP tools."""
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available tools."""
            return [
                Tool(
                    name="initialize_session",
                    description="Initialize a new legal consultation session with case and lawyer information",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "case_info": {
                                "type": "object",
                                "properties": {
                                    "case_id": {"type": "string"},
                                    "caption": {"type": "string"},
                                    "court": {"type": "string"},
                                    "jurisdiction": {"type": "string"},
                                    "case_type": {"type": "string"},
                                    "filed_date": {"type": "string", "format": "date-time"},
                                    "judge_name": {"type": "string"},
                                    "our_role": {"type": "string", "enum": ["plaintiff", "defendant", "appellant", "appellee"]},
                                    "key_issues": {"type": "array", "items": {"type": "string"}},
                                    "current_stage": {"type": "string"}
                                }
                            },
                            "lawyer_info": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "name": {"type": "string"},
                                    "firm": {"type": "string"},
                                    "bar_id": {"type": "string"},
                                    "specializations": {"type": "array", "items": {"type": "string"}},
                                    "years_experience": {"type": "integer"}
                                }
                            },
                            "opposing_counsel_info": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "name": {"type": "string"},
                                    "firm": {"type": "string"},
                                    "bar_id": {"type": "string"},
                                    "specializations": {"type": "array", "items": {"type": "string"}},
                                    "years_experience": {"type": "integer"}
                                }
                            },
                            "session_id": {"type": "string", "description": "Optional session ID to use"}
                        }
                    }
                ),
                Tool(
                    name="consult_lawyer",
                    description="Consult with the AI lawyer agent for legal advice and analysis",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The legal question or argument to discuss"
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID from initialize_session"
                            },
                            "include_precedents": {
                                "type": "boolean",
                                "description": "Whether to search for and include relevant precedents",
                                "default": True
                            },
                            "simulate_opposition": {
                                "type": "boolean",
                                "description": "Whether to simulate opposing counsel's response",
                                "default": False
                            }
                        },
                        "required": ["query", "session_id"]
                    }
                ),
                Tool(
                    name="simulate_opponent",
                    description="Simulate opposing counsel's response to your argument",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "our_argument": {
                                "type": "string",
                                "description": "Our legal argument to counter"
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID for context"
                            }
                        },
                        "required": ["our_argument", "session_id"]
                    }
                ),
                Tool(
                    name="analyze_case",
                    description="Perform deep analysis of the case based on current session context",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "Session ID for analysis"
                            },
                            "deep_analysis": {
                                "type": "boolean",
                                "description": "Whether to perform deep analysis",
                                "default": True
                            }
                        },
                        "required": ["session_id"]
                    }
                ),
                Tool(
                    name="get_relevant_precedents",
                    description="Search for relevant legal precedents",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "search_query": {
                                "type": "string",
                                "description": "Legal issue or query to search for"
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Optional session ID for context"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of precedents to return",
                                "default": 5,
                                "minimum": 1,
                                "maximum": 20
                            }
                        },
                        "required": ["search_query"]
                    }
                ),
                Tool(
                    name="get_session_summary",
                    description="Get a summary of the current session including case info and conversation history",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "Session ID to summarize"
                            }
                        },
                        "required": ["session_id"]
                    }
                ),
                Tool(
                    name="end_session",
                    description="End a legal consultation session",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "Session ID to end"
                            },
                            "export_data": {
                                "type": "boolean",
                                "description": "Whether to export session data before ending",
                                "default": False
                            }
                        },
                        "required": ["session_id"]
                    }
                )
            ]
            
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls."""
            try:
                if name == "initialize_session":
                    result = await self._initialize_session(arguments)
                elif name == "consult_lawyer":
                    result = await self._consult_lawyer(arguments)
                elif name == "simulate_opponent":
                    result = await self._simulate_opponent(arguments)
                elif name == "analyze_case":
                    result = await self._analyze_case(arguments)
                elif name == "get_relevant_precedents":
                    result = await self._get_relevant_precedents(arguments)
                elif name == "get_session_summary":
                    result = await self._get_session_summary(arguments)
                elif name == "end_session":
                    result = await self._end_session(arguments)
                else:
                    result = {"error": f"Unknown tool: {name}"}
                    
                return [TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str)
                )]
                
            except Exception as e:
                logger.error(f"Error in tool {name}: {e}", exc_info=True)
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": str(e),
                        "tool": name
                    }, indent=2)
                )]
                
    async def _initialize_session(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Initialize a new session.
        
        Args:
            arguments: Tool arguments
            
        Returns:
            Session initialization result
        """
        try:
            # Parse case info
            case_info = None
            if "case_info" in arguments and arguments["case_info"]:
                case_data = arguments["case_info"]
                case_info = CaseInfo(
                    case_id=case_data.get("case_id", f"case_{datetime.now().timestamp()}"),
                    caption=case_data.get("caption", "Untitled Case"),
                    court=case_data.get("court", "Court"),
                    jurisdiction=case_data.get("jurisdiction", "US"),
                    case_type=case_data.get("case_type", "Civil"),
                    filed_date=datetime.fromisoformat(case_data["filed_date"]) if "filed_date" in case_data else datetime.now(),
                    judge_name=case_data.get("judge_name"),
                    judge_id=case_data.get("judge_id"),
                    our_role=PartyRole(case_data["our_role"]) if "our_role" in case_data else None,
                    key_issues=case_data.get("key_issues", []),
                    current_stage=case_data.get("current_stage")
                )
                
            # Parse lawyer info
            lawyer_info = None
            if "lawyer_info" in arguments and arguments["lawyer_info"]:
                lawyer_data = arguments["lawyer_info"]
                lawyer_info = LawyerInfo(
                    id=lawyer_data.get("id", f"lawyer_{datetime.now().timestamp()}"),
                    name=lawyer_data.get("name", "Attorney"),
                    firm=lawyer_data.get("firm"),
                    bar_id=lawyer_data.get("bar_id"),
                    specializations=lawyer_data.get("specializations", []),
                    years_experience=lawyer_data.get("years_experience")
                )
                
            # Parse opposing counsel info
            opposing_counsel = None
            if "opposing_counsel_info" in arguments and arguments["opposing_counsel_info"]:
                counsel_data = arguments["opposing_counsel_info"]
                opposing_counsel = LawyerInfo(
                    id=counsel_data.get("id", f"opp_{datetime.now().timestamp()}"),
                    name=counsel_data.get("name", "Opposing Counsel"),
                    firm=counsel_data.get("firm"),
                    bar_id=counsel_data.get("bar_id"),
                    specializations=counsel_data.get("specializations", []),
                    years_experience=counsel_data.get("years_experience")
                )
                
            # Create session
            session = await self.conversation_manager.create_session(
                case_info=case_info,
                our_lawyer=lawyer_info,
                opposing_counsel=opposing_counsel,
                session_id=arguments.get("session_id")
            )
            
            return {
                "success": True,
                "session_id": session.session_id,
                "message": "Session initialized successfully",
                "context_summary": session.context.get_context_summary()
            }
            
        except Exception as e:
            logger.error(f"Error initializing session: {e}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def _consult_lawyer(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Consult with the lawyer agent.
        
        Args:
            arguments: Tool arguments
            
        Returns:
            Consultation response
        """
        try:
            session_id = arguments["session_id"]
            query = arguments["query"]
            include_precedents = arguments.get("include_precedents", True)
            simulate_opposition = arguments.get("simulate_opposition", False)
            
            # Get session
            session = await self.conversation_manager.get_session(session_id)
            if not session:
                return {
                    "success": False,
                    "error": f"Session {session_id} not found or expired"
                }
                
            # Add user query to conversation
            await self.conversation_manager.add_conversation_turn(
                session_id=session_id,
                role="user",
                message=query
            )
            
            # Consult lawyer agent
            response = await self.lawyer_agent.consult(
                query=query,
                context=session.context,
                include_precedents=include_precedents,
                simulate_opposition=simulate_opposition and self.config["features"]["opponent_simulation"]
            )
            
            # Add lawyer response to conversation
            await self.conversation_manager.add_conversation_turn(
                session_id=session_id,
                role="lawyer",
                message=response["lawyer_response"]["argument"],
                metadata={"full_response": response}
            )
            
            # If opposition was simulated, add that too
            if response.get("opposition_analysis"):
                await self.conversation_manager.add_conversation_turn(
                    session_id=session_id,
                    role="opponent",
                    message=response["opposition_analysis"]["opposing_argument"],
                    metadata={"analysis": response["opposition_analysis"]}
                )
                
            return {
                "success": True,
                "response": response
            }
            
        except Exception as e:
            logger.error(f"Error in lawyer consultation: {e}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def _simulate_opponent(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate opposing counsel's response.
        
        Args:
            arguments: Tool arguments
            
        Returns:
            Opposition simulation
        """
        try:
            if not self.config["features"]["opponent_simulation"]:
                return {
                    "success": False,
                    "error": "Opponent simulation feature is disabled"
                }
                
            session_id = arguments["session_id"]
            our_argument = arguments["our_argument"]
            
            # Get session
            session = await self.conversation_manager.get_session(session_id)
            if not session:
                return {
                    "success": False,
                    "error": f"Session {session_id} not found or expired"
                }
                
            # Simulate opposition
            opposition_analysis = await self.lawyer_agent.opponent_simulator.simulate_opponent_response(
                our_argument=our_argument,
                case_context=session.context.case_info.to_dict() if session.context.case_info else {},
                opposing_counsel=session.context.opposing_counsel,
                our_position=session.context.case_info.our_role.value if session.context.case_info and session.context.case_info.our_role else None
            )
            
            # Add to conversation
            await self.conversation_manager.add_conversation_turn(
                session_id=session_id,
                role="opponent_simulation",
                message=opposition_analysis["opposing_argument"],
                metadata=opposition_analysis
            )
            
            return {
                "success": True,
                "opposition_analysis": opposition_analysis
            }
            
        except Exception as e:
            logger.error(f"Error in opponent simulation: {e}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def _analyze_case(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze the case.
        
        Args:
            arguments: Tool arguments
            
        Returns:
            Case analysis
        """
        try:
            if not self.config["features"]["case_analysis"]:
                return {
                    "success": False,
                    "error": "Case analysis feature is disabled"
                }
                
            session_id = arguments["session_id"]
            deep_analysis = arguments.get("deep_analysis", True)
            
            # Get session
            session = await self.conversation_manager.get_session(session_id)
            if not session:
                return {
                    "success": False,
                    "error": f"Session {session_id} not found or expired"
                }
                
            # Perform analysis
            analysis = await self.lawyer_agent.analyze_case(
                context=session.context,
                deep_analysis=deep_analysis
            )
            
            return {
                "success": True,
                "analysis": analysis
            }
            
        except Exception as e:
            logger.error(f"Error in case analysis: {e}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def _get_relevant_precedents(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get relevant precedents.
        
        Args:
            arguments: Tool arguments
            
        Returns:
            Precedent search results
        """
        try:
            if not self.config["features"]["precedent_search"]:
                return {
                    "success": False,
                    "error": "Precedent search feature is disabled"
                }
                
            search_query = arguments["search_query"]
            session_id = arguments.get("session_id")
            limit = min(arguments.get("limit", 5), 20)
            
            # Get context if session provided
            context = None
            if session_id:
                session = await self.conversation_manager.get_session(session_id)
                if session:
                    context = session.context
                    
            # If no context, create minimal one
            if not context:
                from .legal_context import LegalContext
                context = LegalContext(session_id="temp_search")
                
            # Search precedents
            precedents = await self.lawyer_agent._retrieve_precedents(
                query=search_query,
                context=context
            )
            
            # Format results
            formatted_precedents = []
            for p in precedents[:limit]:
                formatted_precedents.append({
                    "case": p.get("case", {}),
                    "issue": p.get("issue", {}),
                    "confidence": p.get("confidence", {}),
                    "key_argument": p.get("segments", [{}])[0].get("text", "")[:300] if p.get("segments") else "",
                    "citations": [seg.get("citations", []) for seg in p.get("segments", [])]
                })
                
            return {
                "success": True,
                "precedents": formatted_precedents,
                "total_found": len(precedents),
                "returned": len(formatted_precedents)
            }
            
        except Exception as e:
            logger.error(f"Error in precedent search: {e}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def _get_session_summary(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get session summary.
        
        Args:
            arguments: Tool arguments
            
        Returns:
            Session summary
        """
        try:
            session_id = arguments["session_id"]
            
            # Get session summary
            summary = await self.conversation_manager.get_session_summary(session_id)
            if not summary:
                return {
                    "success": False,
                    "error": f"Session {session_id} not found or expired"
                }
                
            # Get conversation history
            history = await self.conversation_manager.get_session_history(session_id, n=10)
            
            return {
                "success": True,
                "summary": summary,
                "recent_conversation": history
            }
            
        except Exception as e:
            logger.error(f"Error getting session summary: {e}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def _end_session(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """End a session.
        
        Args:
            arguments: Tool arguments
            
        Returns:
            Session end result
        """
        try:
            session_id = arguments["session_id"]
            export_data = arguments.get("export_data", False)
            
            # Export if requested
            exported_data = None
            if export_data:
                exported_data = await self.conversation_manager.export_session(session_id)
                
            # End session
            success = await self.conversation_manager.end_session(session_id)
            
            if not success:
                return {
                    "success": False,
                    "error": f"Session {session_id} not found"
                }
                
            return {
                "success": True,
                "message": f"Session {session_id} ended successfully",
                "exported_data": exported_data
            }
            
        except Exception as e:
            logger.error(f"Error ending session: {e}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def start(self):
        """Start the MCP server."""
        try:
            # Start conversation manager
            await self.conversation_manager.start()
            
            logger.info("MCP Lawyer Server started successfully")
            
            # Run stdio server
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options()
                )
                
        except Exception as e:
            logger.error(f"Error starting server: {e}")
            raise
            
    async def stop(self):
        """Stop the MCP server."""
        try:
            # Stop conversation manager
            await self.conversation_manager.stop()
            
            logger.info("MCP Lawyer Server stopped")
            
        except Exception as e:
            logger.error(f"Error stopping server: {e}")


async def main():
    """Main entry point."""
    # Get config path from environment or use default
    config_path = os.getenv("MCP_CONFIG_PATH", "mcp_lawyer_server/config.yaml")
    
    # Create and start server
    server = MCPLawyerServer(config_path)
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())