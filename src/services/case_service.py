"""
Case Service - Business logic for case management.

This module provides the service layer for case management operations,
including CRUD operations, document management, and analysis session handling.
"""

import json
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class CaseService:
    """Service class for case management operations."""
    
    def __init__(self):
        # For now, use in-memory storage. In production, this would use a database.
        self.cases: Dict[str, Dict[str, Any]] = {}
        self.documents: Dict[str, List[Dict[str, Any]]] = {}  # case_id -> documents
        self.analysis_sessions: Dict[str, Dict[str, Any]] = {}
        
        # Try to load from persistence file
        self.persistence_file = Path(__file__).parent.parent.parent / "data" / "cases.json"
        self._load_persistence()
    
    def _load_persistence(self):
        """Load data from persistence file if it exists."""
        if self.persistence_file.exists():
            try:
                with open(self.persistence_file, 'r') as f:
                    data = json.load(f)
                    self.cases = data.get('cases', {})
                    self.documents = data.get('documents', {})
                    self.analysis_sessions = data.get('analysis_sessions', {})
                logger.info(f"Loaded {len(self.cases)} cases from persistence")
            except Exception as e:
                logger.warning(f"Failed to load persistence: {e}")
    
    def _save_persistence(self):
        """Save data to persistence file."""
        try:
            self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persistence_file, 'w') as f:
                json.dump({
                    'cases': self.cases,
                    'documents': self.documents,
                    'analysis_sessions': self.analysis_sessions
                }, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to save persistence: {e}")
    
    async def create_case(self, case_id: str, case_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new case."""
        try:
            now = datetime.now()
            
            # Create case record
            case = {
                "id": case_id,
                "title": case_data.get("title"),
                "description": case_data.get("description"),
                "status": "draft",
                "parties": case_data.get("parties", []),
                "court_info": case_data.get("court_info"),
                "issues": case_data.get("issues", []),
                "extraction_method": case_data.get("extraction_method"),
                "extraction_session_id": case_data.get("extraction_session_id"),
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "created_by": case_data.get("created_by")
            }
            
            # Initialize empty collections
            case["documents"] = []
            case["timeline"] = [{
                "id": str(uuid.uuid4()),
                "date": now.isoformat(),
                "event_type": "case_created",
                "description": f"Case created via {case_data.get('extraction_method', 'manual')}",
                "created_by": case_data.get("created_by")
            }]
            
            self.cases[case_id] = case
            self.documents[case_id] = []
            
            self._save_persistence()
            
            logger.info(f"Created case {case_id}: {case.get('title')}")
            return case
            
        except Exception as e:
            logger.error(f"Error creating case: {e}")
            return None
    
    async def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Get a case by ID."""
        return self.cases.get(case_id)
    
    async def update_case(self, case_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a case."""
        if case_id not in self.cases:
            return None
        
        try:
            case = self.cases[case_id]
            
            # Update fields
            for key, value in updates.items():
                if key not in ['id', 'created_at']:  # Don't allow updating these
                    case[key] = value
            
            case["updated_at"] = datetime.now().isoformat()
            
            # Add timeline entry for status changes
            if "status" in updates:
                timeline_entry = {
                    "id": str(uuid.uuid4()),
                    "date": datetime.now().isoformat(),
                    "event_type": "status_changed",
                    "description": f"Status changed to {updates['status']}",
                    "created_by": updates.get("updated_by")
                }
                case["timeline"].append(timeline_entry)
            
            self._save_persistence()
            
            logger.info(f"Updated case {case_id}")
            return case
            
        except Exception as e:
            logger.error(f"Error updating case {case_id}: {e}")
            return None
    
    async def delete_case(self, case_id: str) -> bool:
        """Delete a case."""
        if case_id not in self.cases:
            return False
        
        try:
            del self.cases[case_id]
            if case_id in self.documents:
                del self.documents[case_id]
            
            # Remove related analysis sessions
            sessions_to_remove = [
                session_id for session_id, session in self.analysis_sessions.items()
                if session.get("case_id") == case_id
            ]
            for session_id in sessions_to_remove:
                del self.analysis_sessions[session_id]
            
            self._save_persistence()
            
            logger.info(f"Deleted case {case_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting case {case_id}: {e}")
            return False
    
    async def list_cases(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List cases with optional filtering."""
        cases = list(self.cases.values())
        
        # Apply filters
        if status:
            cases = [case for case in cases if case.get("status") == status]
        
        if created_by:
            cases = [case for case in cases if case.get("created_by") == created_by]
        
        # Sort by created_at descending
        cases.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        # Apply pagination
        return cases[skip:skip + limit]
    
    async def count_cases(
        self,
        status: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> int:
        """Count cases with optional filtering."""
        cases = list(self.cases.values())
        
        # Apply filters
        if status:
            cases = [case for case in cases if case.get("status") == status]
        
        if created_by:
            cases = [case for case in cases if case.get("created_by") == created_by]
        
        return len(cases)
    
    async def add_document(self, case_id: str, document_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a document to a case."""
        if case_id not in self.cases:
            return None
        
        try:
            document = {
                "id": str(uuid.uuid4()),
                "filename": document_info.get("filename"),
                "file_type": document_info.get("file_type"),
                "upload_date": datetime.now().isoformat(),
                "extracted_data": document_info.get("extracted_data"),
                "case_id": case_id
            }
            
            if case_id not in self.documents:
                self.documents[case_id] = []
            
            self.documents[case_id].append(document)
            
            # Update case timeline
            case = self.cases[case_id]
            timeline_entry = {
                "id": str(uuid.uuid4()),
                "date": datetime.now().isoformat(),
                "event_type": "document_added",
                "description": f"Document added: {document_info.get('filename')}",
                "created_by": document_info.get("uploaded_by")
            }
            case["timeline"].append(timeline_entry)
            case["updated_at"] = datetime.now().isoformat()
            
            self._save_persistence()
            
            logger.info(f"Added document to case {case_id}: {document['id']}")
            return document
            
        except Exception as e:
            logger.error(f"Error adding document to case {case_id}: {e}")
            return None
    
    async def get_documents(self, case_id: str) -> List[Dict[str, Any]]:
        """Get all documents for a case."""
        return self.documents.get(case_id, [])
    
    async def save_analysis_session(self, session_id: str, session_data: Dict[str, Any]) -> bool:
        """Save an analysis session."""
        try:
            self.analysis_sessions[session_id] = session_data
            self._save_persistence()
            
            logger.info(f"Saved analysis session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving analysis session {session_id}: {e}")
            return False
    
    async def get_analysis_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get an analysis session by ID."""
        return self.analysis_sessions.get(session_id)
    
    async def update_analysis_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update an analysis session."""
        if session_id not in self.analysis_sessions:
            return False
        
        try:
            session = self.analysis_sessions[session_id]
            session.update(updates)
            session["last_updated"] = datetime.now().isoformat()
            
            self._save_persistence()
            
            logger.info(f"Updated analysis session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating analysis session {session_id}: {e}")
            return False
    
    async def get_case_analysis_sessions(self, case_id: str) -> List[Dict[str, Any]]:
        """Get all analysis sessions for a case."""
        sessions = [
            session for session in self.analysis_sessions.values()
            if session.get("case_id") == case_id
        ]
        
        # Sort by started_at descending
        sessions.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        
        return sessions


# Global case service instance
case_service = CaseService()