"""
Chatbox agent for conversational case information extraction.

This module implements an intelligent conversational agent that guides users
through providing case information via natural dialogue.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import openai
from openai import AsyncOpenAI

from .models import (
    ExtractedCaseInfo,
    ChatboxState,
    Party,
    PartyType,
    CourtInfo,
    LegalIssue,
    ReliefSought,
    DocumentReference,
    CaseType,
    CaseStage
)
from .validators import CaseInfoValidator


logger = logging.getLogger(__name__)


class ChatboxAgent:
    """Conversational agent for extracting case information."""
    
    # Question templates for different fields
    QUESTION_TEMPLATES = {
        'case_number': "What is the case number or docket number? (If you don't have it, just say 'skip')",
        'case_title': "What is the case title or caption? (e.g., 'Smith v. Jones')",
        'filing_date': "When was this case filed? Please provide the date if known.",
        'case_type': "What type of case is this? (civil, criminal, family, bankruptcy, administrative, appeal, or other)",
        'case_stage': "What stage is the case currently in? (filing, discovery, motion practice, trial, appeal, etc.)",
        'parties': "Who are the parties involved? Please list the plaintiffs/petitioners and defendants/respondents.",
        'court_info': "Which court is handling this case? Include the court name and location if known.",
        'judge': "Who is the presiding judge, if known?",
        'legal_issues': "What are the main legal issues or claims in this case?",
        'fact_summary': "Can you provide a brief summary of the key facts?",
        'disputed_facts': "Are there any disputed facts? If so, what are they?",
        'relief_sought': "What relief or remedies are being sought? (monetary damages, injunction, etc.)",
        'document_references': "Are there any important cases, statutes, or regulations cited?",
    }
    
    # Follow-up question templates
    FOLLOW_UP_TEMPLATES = {
        'parties': {
            'attorneys': "Do you know the attorneys representing each party?",
            'contact': "Do you have contact information for any of the parties?",
        },
        'court_info': {
            'jurisdiction': "Is this a federal or state court?",
            'department': "Do you know the department or division?",
        },
        'relief_sought': {
            'amount': "What is the amount of monetary damages sought?",
            'specifics': "Can you provide more details about the relief requested?",
        }
    }
    
    # Field priority order
    FIELD_PRIORITY = [
        'case_title',  # Most important
        'case_type',
        'parties',
        'legal_issues',
        'case_number',
        'court_info',
        'filing_date',
        'fact_summary',
        'relief_sought',
        'case_stage',
        'disputed_facts',
        'document_references',
    ]
    
    def __init__(self, openai_api_key: Optional[str] = None, config: Optional[Dict] = None):
        """Initialize the chatbox agent."""
        self.config = config or {}
        self.client = AsyncOpenAI(api_key=openai_api_key) if openai_api_key else None
        self.max_questions = self.config.get('max_questions', 15)
        self.confidence_threshold = self.config.get('confidence_threshold', 0.7)
        self.use_llm = self.client is not None
        
    async def start_session(self, session_id: str) -> ChatboxState:
        """Initialize a new chatbox session."""
        state = ChatboxState(
            current_field=None,
            fields_completed=[],
            fields_pending=self.FIELD_PRIORITY.copy(),
            question_count=0,
            last_question=None,
            context={}
        )
        
        # Generate initial greeting
        greeting = (
            "Hello! I'll help you extract case information. "
            "I'll ask you a series of questions about the case. "
            "You can say 'skip' if you don't have certain information, "
            "or 'stop' if you want to finish early.\n\n"
            "Let's begin!"
        )
        
        state.context['greeting'] = greeting
        return state
    
    def get_next_question(self, state: ChatboxState, case_info: ExtractedCaseInfo) -> Optional[str]:
        """Generate the next question based on current state."""
        if state.question_count >= self.max_questions:
            return None
        
        if not state.fields_pending:
            return None
        
        # Get next field to ask about
        next_field = state.fields_pending[0]
        
        # Check if we already have this information
        if self._field_is_complete(next_field, case_info):
            state.fields_pending.remove(next_field)
            state.fields_completed.append(next_field)
            return self.get_next_question(state, case_info)
        
        # Generate question
        question = self.QUESTION_TEMPLATES.get(next_field)
        if question:
            state.current_field = next_field
            state.last_question = question
            state.question_count += 1
            return question
        
        return None
    
    async def process_response(
        self, 
        response: str, 
        state: ChatboxState, 
        case_info: ExtractedCaseInfo
    ) -> Tuple[ExtractedCaseInfo, Optional[str], bool]:
        """
        Process user response and extract information.
        
        Returns:
            Tuple of (updated_case_info, next_question, is_complete)
        """
        # Handle control commands
        if response.lower().strip() in ['stop', 'done', 'finish']:
            return case_info, None, True
        
        if response.lower().strip() == 'skip':
            # Move to next field
            if state.current_field and state.current_field in state.fields_pending:
                state.fields_pending.remove(state.current_field)
                state.fields_completed.append(state.current_field)
            next_question = self.get_next_question(state, case_info)
            return case_info, next_question, next_question is None
        
        # Extract information from response
        if state.current_field:
            if self.use_llm:
                # Use LLM to extract structured information
                extracted_data = await self._extract_with_llm(
                    response, 
                    state.current_field,
                    state.context
                )
                case_info = self._update_case_info(case_info, state.current_field, extracted_data)
            else:
                # Use rule-based extraction
                case_info = self._extract_with_rules(case_info, state.current_field, response)
            
            # Mark field as completed
            if state.current_field in state.fields_pending:
                state.fields_pending.remove(state.current_field)
                state.fields_completed.append(state.current_field)
        
        # Check if follow-up questions are needed
        follow_up = self._get_follow_up_question(state, case_info)
        if follow_up:
            state.question_count += 1
            state.last_question = follow_up
            return case_info, follow_up, False
        
        # Get next question
        next_question = self.get_next_question(state, case_info)
        is_complete = next_question is None or state.question_count >= self.max_questions
        
        return case_info, next_question, is_complete
    
    async def _extract_with_llm(
        self, 
        response: str, 
        field: str, 
        context: Dict
    ) -> Dict[str, Any]:
        """Use LLM to extract structured information from response."""
        if not self.client:
            return {'raw_text': response}
        
        # Create extraction prompt
        system_prompt = f"""You are a legal information extraction assistant.
        Extract structured information from the user's response for the field: {field}
        
        Return a JSON object with the extracted information.
        Be precise and only extract what is explicitly stated.
        """
        
        field_prompts = {
            'case_number': "Extract the case number. Return: {\"case_number\": \"extracted_number\"}",
            'case_title': "Extract the case title. Return: {\"case_title\": \"Party1 v. Party2\"}",
            'filing_date': "Extract the filing date. Return: {\"filing_date\": \"YYYY-MM-DD\"}",
            'case_type': "Identify the case type (civil/criminal/family/etc). Return: {\"case_type\": \"type\"}",
            'parties': """Extract all parties mentioned. Return: {
                \"plaintiffs\": [{"name": "...", "attorneys": [...]}],
                \"defendants\": [{"name": "...", "attorneys": [...]}]
            }""",
            'court_info': """Extract court information. Return: {
                \"court_name\": "...",
                \"jurisdiction\": "federal/state",
                \"location\": "...",
                \"judge\": "..."
            }""",
            'legal_issues': """Extract legal issues. Return: {
                \"issues\": [
                    {"issue": "...", "category": "...", "is_primary": true/false}
                ]
            }""",
            'relief_sought': """Extract relief sought. Return: {
                \"monetary_damages\": 0.0,
                \"injunctive_relief\": "...",
                \"other_relief\": [...]
            }"""
        }
        
        user_prompt = field_prompts.get(field, f"Extract information for {field} from: {response}")
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"User response: {response}\n\n{user_prompt}"}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return {'raw_text': response}
    
    def _extract_with_rules(
        self, 
        case_info: ExtractedCaseInfo, 
        field: str, 
        response: str
    ) -> ExtractedCaseInfo:
        """Extract information using rule-based approach."""
        response = response.strip()
        
        if field == 'case_number':
            case_info.case_number = response
            
        elif field == 'case_title':
            case_info.case_title = response
            
        elif field == 'filing_date':
            # Try to parse date
            try:
                # Simple date parsing - could be enhanced
                from dateutil import parser
                case_info.filing_date = parser.parse(response)
            except:
                pass
                
        elif field == 'case_type':
            # Map response to CaseType enum
            type_map = {
                'civil': CaseType.CIVIL,
                'criminal': CaseType.CRIMINAL,
                'family': CaseType.FAMILY,
                'bankruptcy': CaseType.BANKRUPTCY,
                'administrative': CaseType.ADMINISTRATIVE,
                'appeal': CaseType.APPEAL,
            }
            case_type = type_map.get(response.lower(), CaseType.OTHER)
            case_info.case_type = case_type
            
        elif field == 'parties':
            # Simple party extraction
            lines = response.split('\n')
            for line in lines:
                line_lower = line.lower()
                if 'plaintiff' in line_lower or 'petitioner' in line_lower:
                    party = Party(
                        name=line.split(':')[-1].strip() if ':' in line else line,
                        party_type=PartyType.PLAINTIFF
                    )
                    case_info.parties.append(party)
                elif 'defendant' in line_lower or 'respondent' in line_lower:
                    party = Party(
                        name=line.split(':')[-1].strip() if ':' in line else line,
                        party_type=PartyType.DEFENDANT
                    )
                    case_info.parties.append(party)
                    
        elif field == 'court_info':
            case_info.court_info = CourtInfo(
                name=response,
                jurisdiction='unknown'
            )
            
        elif field == 'legal_issues':
            # Create a primary legal issue from the response
            issue = LegalIssue(
                issue=response,
                category='general',
                is_primary=True
            )
            case_info.legal_issues.append(issue)
            
        elif field == 'fact_summary':
            case_info.fact_summary = response
            
        elif field == 'relief_sought':
            case_info.relief_sought = ReliefSought(other_relief=[response])
            
        return case_info
    
    def _update_case_info(
        self, 
        case_info: ExtractedCaseInfo, 
        field: str, 
        extracted_data: Dict
    ) -> ExtractedCaseInfo:
        """Update case info with extracted data."""
        if field == 'case_number':
            case_info.case_number = extracted_data.get('case_number')
            
        elif field == 'case_title':
            case_info.case_title = extracted_data.get('case_title')
            
        elif field == 'filing_date':
            date_str = extracted_data.get('filing_date')
            if date_str:
                try:
                    from dateutil import parser
                    case_info.filing_date = parser.parse(date_str)
                except:
                    pass
                    
        elif field == 'case_type':
            case_type_str = extracted_data.get('case_type', '').lower()
            for case_type in CaseType:
                if case_type.value == case_type_str:
                    case_info.case_type = case_type
                    break
                    
        elif field == 'parties':
            # Process plaintiffs
            for p_data in extracted_data.get('plaintiffs', []):
                party = Party(
                    name=p_data.get('name', 'Unknown'),
                    party_type=PartyType.PLAINTIFF,
                    attorneys=p_data.get('attorneys', [])
                )
                case_info.parties.append(party)
            
            # Process defendants
            for d_data in extracted_data.get('defendants', []):
                party = Party(
                    name=d_data.get('name', 'Unknown'),
                    party_type=PartyType.DEFENDANT,
                    attorneys=d_data.get('attorneys', [])
                )
                case_info.parties.append(party)
                
        elif field == 'court_info':
            court_data = extracted_data
            case_info.court_info = CourtInfo(
                name=court_data.get('court_name', 'Unknown Court'),
                jurisdiction=court_data.get('jurisdiction', 'unknown'),
                location=court_data.get('location'),
                judge=court_data.get('judge')
            )
            
        elif field == 'legal_issues':
            for issue_data in extracted_data.get('issues', []):
                issue = LegalIssue(
                    issue=issue_data.get('issue', ''),
                    category=issue_data.get('category', 'general'),
                    is_primary=issue_data.get('is_primary', False)
                )
                case_info.legal_issues.append(issue)
                
        elif field == 'relief_sought':
            case_info.relief_sought = ReliefSought(
                monetary_damages=extracted_data.get('monetary_damages'),
                injunctive_relief=extracted_data.get('injunctive_relief'),
                other_relief=extracted_data.get('other_relief', [])
            )
            
        return case_info
    
    def _field_is_complete(self, field: str, case_info: ExtractedCaseInfo) -> bool:
        """Check if a field has already been filled."""
        value = getattr(case_info, field, None)
        if value is None:
            return False
        if isinstance(value, list):
            return len(value) > 0
        if isinstance(value, str):
            return len(value.strip()) > 0
        return True
    
    def _get_follow_up_question(
        self, 
        state: ChatboxState, 
        case_info: ExtractedCaseInfo
    ) -> Optional[str]:
        """Generate follow-up questions for additional details."""
        # Only ask follow-ups for important fields and if we haven't asked too many questions
        if state.question_count >= self.max_questions - 3:
            return None
        
        # Check if we need attorney information for parties
        if state.current_field == 'parties' and case_info.parties:
            has_attorneys = any(p.attorneys for p in case_info.parties)
            if not has_attorneys and 'parties_attorneys' not in state.fields_completed:
                state.fields_completed.append('parties_attorneys')
                return self.FOLLOW_UP_TEMPLATES['parties']['attorneys']
        
        # Check if we need jurisdiction for court
        if state.current_field == 'court_info' and case_info.court_info:
            if case_info.court_info.jurisdiction == 'unknown':
                return self.FOLLOW_UP_TEMPLATES['court_info']['jurisdiction']
        
        return None
    
    def calculate_extraction_confidence(
        self, 
        case_info: ExtractedCaseInfo,
        state: ChatboxState
    ) -> float:
        """Calculate confidence score for the extraction."""
        # Base confidence on completeness and question count
        completeness = CaseInfoValidator.calculate_completeness_score(case_info)
        
        # Adjust based on number of fields completed
        field_ratio = len(state.fields_completed) / len(self.FIELD_PRIORITY)
        
        # Penalize if too few questions were answered
        question_penalty = 0 if state.question_count >= 5 else 0.2
        
        confidence = (completeness * 0.6 + field_ratio * 0.4) - question_penalty
        return max(0.0, min(1.0, confidence))