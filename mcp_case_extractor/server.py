"""
MCP Server for legal case information extraction.

This module implements the Model Context Protocol server that provides
tools for extracting case information through chatbox and file parsing.
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)

from .models import (
    ExtractedCaseInfo,
    ExtractionSession,
    ChatboxState,
    Party,
    CourtInfo,
    LegalIssue
)
from .chatbox_agent import ChatboxAgent
from .file_parser import FileParser
from .validators import CaseInfoValidator
from .integrations import IntegrationManager


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CaseExtractorServer:
    """MCP Server for case information extraction."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the case extractor server."""
        self.server = Server("case-extractor")
        self.sessions: Dict[str, ExtractionSession] = {}
        self.config = self._load_config(config_path)
        
        # Initialize components
        openai_key = self.config.get('openai_api_key')
        self.chatbox_agent = ChatboxAgent(openai_key, self.config.get('chatbox', {}))
        self.file_parser = FileParser(openai_key, self.config.get('parser', {}))
        self.integration_manager = IntegrationManager(self.config.get('integrations', {}))
        
        # Register handlers
        self._register_handlers()
        
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Load configuration from file."""
        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                    import yaml
                    return yaml.safe_load(f)
                else:
                    return json.load(f)
        return {}
    
    def _register_handlers(self):
        """Register MCP protocol handlers."""
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available tools."""
            return [
                Tool(
                    name="start_chatbox_extraction",
                    description="Start a conversational extraction session",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "Optional session ID (will be generated if not provided)"
                            }
                        }
                    }
                ),
                Tool(
                    name="chatbox_respond",
                    description="Process user response in chatbox extraction",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "Session ID"
                            },
                            "response": {
                                "type": "string",
                                "description": "User's response to the question"
                            }
                        },
                        "required": ["session_id", "response"]
                    }
                ),
                Tool(
                    name="parse_document",
                    description="Extract case information from a document file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the document file"
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Optional session ID"
                            }
                        },
                        "required": ["file_path"]
                    }
                ),
                Tool(
                    name="parse_batch",
                    description="Parse multiple documents in batch",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of file paths to parse"
                            }
                        },
                        "required": ["file_paths"]
                    }
                ),
                Tool(
                    name="get_extraction_status",
                    description="Get the status of an extraction session",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "Session ID"
                            }
                        },
                        "required": ["session_id"]
                    }
                ),
                Tool(
                    name="validate_extraction",
                    description="Validate extracted case information",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "Session ID"
                            },
                            "validation_level": {
                                "type": "string",
                                "enum": ["minimal", "basic", "standard", "complete"],
                                "description": "Validation level",
                                "default": "standard"
                            }
                        },
                        "required": ["session_id"]
                    }
                ),
                Tool(
                    name="finalize_extraction",
                    description="Complete extraction and send to info fetcher",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "Session ID"
                            },
                            "send_to_fetcher": {
                                "type": "boolean",
                                "description": "Whether to send to info fetcher",
                                "default": True
                            }
                        },
                        "required": ["session_id"]
                    }
                ),
                Tool(
                    name="merge_extractions",
                    description="Merge chatbox and document extractions",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of session IDs to merge"
                            },
                            "strategy": {
                                "type": "string",
                                "enum": ["prefer_chatbox", "prefer_document", "combine"],
                                "description": "Merge strategy",
                                "default": "combine"
                            }
                        },
                        "required": ["session_ids"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[Union[TextContent, ImageContent]]:
            """Handle tool calls."""
            try:
                if name == "start_chatbox_extraction":
                    result = await self._start_chatbox_extraction(
                        arguments.get("session_id")
                    )
                    
                elif name == "chatbox_respond":
                    result = await self._chatbox_respond(
                        arguments["session_id"],
                        arguments["response"]
                    )
                    
                elif name == "parse_document":
                    result = await self._parse_document(
                        arguments["file_path"],
                        arguments.get("session_id")
                    )
                    
                elif name == "parse_batch":
                    result = await self._parse_batch(
                        arguments["file_paths"]
                    )
                    
                elif name == "get_extraction_status":
                    result = await self._get_extraction_status(
                        arguments["session_id"]
                    )
                    
                elif name == "validate_extraction":
                    result = await self._validate_extraction(
                        arguments["session_id"],
                        arguments.get("validation_level", "standard")
                    )
                    
                elif name == "finalize_extraction":
                    result = await self._finalize_extraction(
                        arguments["session_id"],
                        arguments.get("send_to_fetcher", True)
                    )
                    
                elif name == "merge_extractions":
                    result = await self._merge_extractions(
                        arguments["session_ids"],
                        arguments.get("strategy", "combine")
                    )
                    
                else:
                    result = {"error": f"Unknown tool: {name}"}
                
                # Convert result to JSON string for response
                return [TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str)
                )]
                
            except Exception as e:
                logger.error(f"Error in tool {name}: {e}", exc_info=True)
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)}, indent=2)
                )]
    
    async def _start_chatbox_extraction(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Start a new chatbox extraction session."""
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # Initialize chatbox state
        chatbox_state = await self.chatbox_agent.start_session(session_id)
        
        # Create extraction session
        session = ExtractionSession(
            session_id=session_id,
            extraction_type="chatbox",
            status="active",
            extracted_info=ExtractedCaseInfo(extraction_source="chatbox")
        )
        
        # Store session
        self.sessions[session_id] = session
        
        # Get first question
        first_question = self.chatbox_agent.get_next_question(
            chatbox_state,
            session.extracted_info
        )
        
        return {
            "session_id": session_id,
            "status": "active",
            "greeting": chatbox_state.context.get('greeting'),
            "question": first_question,
            "fields_pending": len(chatbox_state.fields_pending),
            "fields_completed": len(chatbox_state.fields_completed)
        }
    
    async def _chatbox_respond(self, session_id: str, response: str) -> Dict[str, Any]:
        """Process user response in chatbox extraction."""
        if session_id not in self.sessions:
            return {"error": f"Session {session_id} not found"}
        
        session = self.sessions[session_id]
        if session.extraction_type != "chatbox":
            return {"error": "Session is not a chatbox extraction"}
        
        if session.status != "active":
            return {"error": f"Session is {session.status}, not active"}
        
        # Get or create chatbox state
        if 'chatbox_state' not in session.__dict__:
            session.chatbox_state = await self.chatbox_agent.start_session(session_id)
        
        # Process response
        updated_info, next_question, is_complete = await self.chatbox_agent.process_response(
            response,
            session.chatbox_state,
            session.extracted_info
        )
        
        # Update session
        session.extracted_info = updated_info
        session.updated_at = datetime.utcnow()
        session.messages.append({
            "timestamp": datetime.utcnow().isoformat(),
            "question": session.chatbox_state.last_question,
            "response": response
        })
        
        if is_complete:
            session.status = "completed"
            # Calculate final confidence
            session.extracted_info.confidence_score = self.chatbox_agent.calculate_extraction_confidence(
                session.extracted_info,
                session.chatbox_state
            )
        
        return {
            "session_id": session_id,
            "status": session.status,
            "question": next_question,
            "is_complete": is_complete,
            "fields_completed": len(session.chatbox_state.fields_completed),
            "fields_pending": len(session.chatbox_state.fields_pending),
            "confidence_score": session.extracted_info.confidence_score
        }
    
    async def _parse_document(self, file_path: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Parse a document and extract case information."""
        if not session_id:
            session_id = str(uuid.uuid4())
        
        try:
            # Parse document
            extracted_info = await self.file_parser.parse_document(file_path)
            
            # Create or update session
            if session_id in self.sessions:
                session = self.sessions[session_id]
                # Merge with existing info if present
                if session.extracted_info:
                    extracted_info = self._merge_case_info(
                        session.extracted_info,
                        extracted_info,
                        "prefer_document"
                    )
            else:
                session = ExtractionSession(
                    session_id=session_id,
                    extraction_type="document",
                    status="completed",
                    extracted_info=extracted_info
                )
                self.sessions[session_id] = session
            
            session.files_processed.append(file_path)
            session.updated_at = datetime.utcnow()
            
            # Get missing fields for improvement suggestions
            missing_fields = CaseInfoValidator.suggest_missing_fields(extracted_info)
            
            return {
                "session_id": session_id,
                "status": "completed",
                "file_path": file_path,
                "document_type": extracted_info.document_type.value if extracted_info.document_type else None,
                "confidence_score": extracted_info.confidence_score,
                "extracted_fields": self._get_extracted_fields_summary(extracted_info),
                "missing_fields": missing_fields
            }
            
        except Exception as e:
            logger.error(f"Error parsing document {file_path}: {e}")
            
            # Create failed session
            session = ExtractionSession(
                session_id=session_id,
                extraction_type="document",
                status="failed",
                extracted_info=ExtractedCaseInfo(extraction_source="document")
            )
            session.error_messages.append(str(e))
            self.sessions[session_id] = session
            
            return {
                "session_id": session_id,
                "status": "failed",
                "error": str(e)
            }
    
    async def _parse_batch(self, file_paths: List[str]) -> Dict[str, Any]:
        """Parse multiple documents in batch."""
        results = []
        session_ids = []
        
        for file_path in file_paths:
            session_id = str(uuid.uuid4())
            session_ids.append(session_id)
            result = await self._parse_document(file_path, session_id)
            results.append(result)
        
        # Count successes and failures
        successful = sum(1 for r in results if r.get("status") == "completed")
        failed = sum(1 for r in results if r.get("status") == "failed")
        
        return {
            "total": len(file_paths),
            "successful": successful,
            "failed": failed,
            "session_ids": session_ids,
            "results": results
        }
    
    async def _get_extraction_status(self, session_id: str) -> Dict[str, Any]:
        """Get the status of an extraction session."""
        if session_id not in self.sessions:
            return {"error": f"Session {session_id} not found"}
        
        session = self.sessions[session_id]
        extracted_info = session.extracted_info
        
        # Calculate completeness
        completeness = CaseInfoValidator.calculate_completeness_score(extracted_info)
        missing_fields = CaseInfoValidator.suggest_missing_fields(extracted_info)
        
        return {
            "session_id": session_id,
            "extraction_type": session.extraction_type,
            "status": session.status,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "completeness_score": completeness,
            "confidence_score": extracted_info.confidence_score,
            "extracted_fields": self._get_extracted_fields_summary(extracted_info),
            "missing_fields": missing_fields,
            "files_processed": session.files_processed,
            "message_count": len(session.messages),
            "errors": session.error_messages
        }
    
    async def _validate_extraction(self, session_id: str, validation_level: str) -> Dict[str, Any]:
        """Validate extracted case information."""
        if session_id not in self.sessions:
            return {"error": f"Session {session_id} not found"}
        
        session = self.sessions[session_id]
        extracted_info = session.extracted_info
        
        # Validate
        is_valid, errors = CaseInfoValidator.validate(
            extracted_info,
            validation_level,
            raise_on_error=False
        )
        
        # Get integration validation
        integration_valid, integration_errors, warnings = CaseInfoValidator.validate_for_integration(
            extracted_info,
            'info_fetcher'
        )
        
        return {
            "session_id": session_id,
            "validation_level": validation_level,
            "is_valid": is_valid,
            "errors": errors,
            "integration_ready": integration_valid,
            "integration_errors": integration_errors,
            "warnings": warnings,
            "completeness_score": CaseInfoValidator.calculate_completeness_score(extracted_info)
        }
    
    async def _finalize_extraction(self, session_id: str, send_to_fetcher: bool) -> Dict[str, Any]:
        """Complete extraction and optionally send to info fetcher."""
        if session_id not in self.sessions:
            return {"error": f"Session {session_id} not found"}
        
        session = self.sessions[session_id]
        
        # Mark as completed if not already
        if session.status == "active":
            session.status = "completed"
            session.updated_at = datetime.utcnow()
        
        result = {
            "session_id": session_id,
            "status": session.status,
            "extraction_summary": self._get_extraction_summary(session.extracted_info)
        }
        
        # Send to integrations if requested
        if send_to_fetcher:
            integration_results = await self.integration_manager.process_extraction(
                session.extracted_info,
                session_id
            )
            result["integration_results"] = integration_results
        
        return result
    
    async def _merge_extractions(self, session_ids: List[str], strategy: str) -> Dict[str, Any]:
        """Merge multiple extraction sessions."""
        if len(session_ids) < 2:
            return {"error": "At least 2 session IDs required for merging"}
        
        # Get all sessions
        sessions = []
        for sid in session_ids:
            if sid not in self.sessions:
                return {"error": f"Session {sid} not found"}
            sessions.append(self.sessions[sid])
        
        # Start with first session's info
        merged_info = sessions[0].extracted_info
        
        # Merge remaining sessions
        for session in sessions[1:]:
            merged_info = self._merge_case_info(
                merged_info,
                session.extracted_info,
                strategy
            )
        
        # Create new merged session
        merged_session_id = str(uuid.uuid4())
        merged_session = ExtractionSession(
            session_id=merged_session_id,
            extraction_type="batch",
            status="completed",
            extracted_info=merged_info
        )
        
        # Copy relevant data from source sessions
        for session in sessions:
            merged_session.files_processed.extend(session.files_processed)
            merged_session.messages.extend(session.messages)
        
        self.sessions[merged_session_id] = merged_session
        
        return {
            "merged_session_id": merged_session_id,
            "source_sessions": session_ids,
            "merge_strategy": strategy,
            "extraction_summary": self._get_extraction_summary(merged_info)
        }
    
    def _merge_case_info(
        self, 
        info1: ExtractedCaseInfo, 
        info2: ExtractedCaseInfo,
        strategy: str
    ) -> ExtractedCaseInfo:
        """Merge two ExtractedCaseInfo objects."""
        if strategy == "prefer_chatbox":
            # Prefer chatbox data, fill gaps with document data
            merged = info1 if info1.extraction_source == "chatbox" else info2
            other = info2 if info1.extraction_source == "chatbox" else info1
        elif strategy == "prefer_document":
            # Prefer document data, fill gaps with chatbox data
            merged = info1 if info1.extraction_source == "document" else info2
            other = info2 if info1.extraction_source == "document" else info1
        else:  # combine
            # Combine both, preferring higher confidence
            merged = info1 if info1.confidence_score >= info2.confidence_score else info2
            other = info2 if info1.confidence_score >= info2.confidence_score else info1
        
        # Fill in missing fields from other
        if not merged.case_number and other.case_number:
            merged.case_number = other.case_number
        if not merged.case_title and other.case_title:
            merged.case_title = other.case_title
        if not merged.filing_date and other.filing_date:
            merged.filing_date = other.filing_date
        if not merged.case_type and other.case_type:
            merged.case_type = other.case_type
        if not merged.case_stage and other.case_stage:
            merged.case_stage = other.case_stage
        
        # Merge lists
        if strategy == "combine":
            # Combine parties (avoid duplicates)
            existing_party_names = {p.name for p in merged.parties}
            for party in other.parties:
                if party.name not in existing_party_names:
                    merged.parties.append(party)
            
            # Combine legal issues
            existing_issues = {issue.issue for issue in merged.legal_issues}
            for issue in other.legal_issues:
                if issue.issue not in existing_issues:
                    merged.legal_issues.append(issue)
            
            # Combine document references
            existing_refs = {ref.citation for ref in merged.document_references}
            for ref in other.document_references:
                if ref.citation not in existing_refs:
                    merged.document_references.append(ref)
        
        # Update metadata
        merged.extraction_source = "merged"
        merged.confidence_score = max(merged.confidence_score, other.confidence_score)
        
        return merged
    
    def _get_extracted_fields_summary(self, info: ExtractedCaseInfo) -> Dict[str, bool]:
        """Get summary of which fields have been extracted."""
        return {
            "case_number": bool(info.case_number),
            "case_title": bool(info.case_title),
            "filing_date": bool(info.filing_date),
            "case_type": bool(info.case_type),
            "case_stage": bool(info.case_stage),
            "parties": len(info.parties) > 0,
            "court_info": bool(info.court_info),
            "legal_issues": len(info.legal_issues) > 0,
            "fact_summary": bool(info.fact_summary),
            "disputed_facts": bool(info.disputed_facts),
            "relief_sought": bool(info.relief_sought),
            "document_references": len(info.document_references) > 0,
        }
    
    def _get_extraction_summary(self, info: ExtractedCaseInfo) -> Dict[str, Any]:
        """Get detailed extraction summary."""
        return {
            "case_number": info.case_number,
            "case_title": info.case_title,
            "filing_date": info.filing_date.isoformat() if info.filing_date else None,
            "case_type": info.case_type.value if info.case_type else None,
            "case_stage": info.case_stage.value if info.case_stage else None,
            "party_count": len(info.parties),
            "plaintiff_count": sum(1 for p in info.parties if p.party_type.value in ['plaintiff', 'petitioner']),
            "defendant_count": sum(1 for p in info.parties if p.party_type.value in ['defendant', 'respondent']),
            "court_name": info.court_info.name if info.court_info else None,
            "judge": info.court_info.judge if info.court_info else None,
            "legal_issue_count": len(info.legal_issues),
            "primary_issues": [i.issue for i in info.legal_issues if i.is_primary],
            "has_fact_summary": bool(info.fact_summary),
            "disputed_fact_count": len(info.disputed_facts) if info.disputed_facts else 0,
            "has_relief_sought": bool(info.relief_sought),
            "citation_count": len(info.document_references),
            "confidence_score": info.confidence_score,
            "extraction_source": info.extraction_source,
            "document_type": info.document_type.value if info.document_type else None
        }
    
    async def run(self):
        """Run the MCP server."""
        logger.info("Starting Case Extractor MCP Server")
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


async def main():
    """Main entry point."""
    import sys
    
    # Get config path from command line if provided
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    
    # Create and run server
    server = CaseExtractorServer(config_path)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())