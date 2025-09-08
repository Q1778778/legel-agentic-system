"""
Regex patterns for extracting information from legal documents.

This module contains compiled regex patterns for identifying
common legal document structures and information.
"""

import re
from typing import Pattern, Dict, List, Optional, Tuple
from datetime import datetime


class LegalPatterns:
    """Collection of regex patterns for legal document parsing."""
    
    # Case number patterns for various jurisdictions
    CASE_NUMBER_PATTERNS: List[Pattern] = [
        # Federal format: 1:21-cv-12345
        re.compile(r'\b\d{1,2}:\d{2}-[a-z]{2}-\d{4,6}\b', re.IGNORECASE),
        # State format: 2021-CV-12345
        re.compile(r'\b\d{4}-[A-Z]{2,4}-\d{4,6}\b', re.IGNORECASE),
        # Alternative format: Case No. 21-12345
        re.compile(r'(?:Case\s+No\.?\s*|Docket\s+No\.?\s*)([A-Z0-9\-\/]+)', re.IGNORECASE),
        # Generic number format
        re.compile(r'\b(?:No\.?\s*)([A-Z]?\d{2,4}[\-\/]\d{3,6}[A-Z]?)\b', re.IGNORECASE),
    ]
    
    # Date patterns
    DATE_PATTERNS: List[Pattern] = [
        # MM/DD/YYYY or MM-DD-YYYY
        re.compile(r'\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\b'),
        # Month DD, YYYY
        re.compile(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b', re.IGNORECASE),
        # DD Month YYYY
        re.compile(r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{4})\b', re.IGNORECASE),
    ]
    
    # Party name patterns
    PARTY_PATTERNS: Dict[str, Pattern] = {
        'plaintiff': re.compile(r'(?:Plaintiff[s]?|Petitioner[s]?|Complainant[s]?)[\s:,]+([^,\n]+?)(?:\s*,|\s*\n|\s*v\.|\s*vs\.)', re.IGNORECASE | re.MULTILINE),
        'defendant': re.compile(r'(?:Defendant[s]?|Respondent[s]?)[\s:,]+([^,\n]+?)(?:\s*,|\s*\n|$)', re.IGNORECASE | re.MULTILINE),
        'versus': re.compile(r'([^,\n]+?)\s+v(?:s)?\.?\s+([^,\n]+)', re.IGNORECASE),
    }
    
    # Attorney patterns
    ATTORNEY_PATTERNS: List[Pattern] = [
        re.compile(r'(?:Attorney[s]?\s+for|Counsel\s+for|Representing)[^:]*:\s*([^\n]+)', re.IGNORECASE),
        re.compile(r'([A-Z][a-z]+\s+[A-Z][a-z]+),?\s+Esq\.?', re.IGNORECASE),
        re.compile(r'(?:State\s+Bar\s+No\.?|Bar\s+No\.?)\s*[:#]?\s*(\d+)', re.IGNORECASE),
    ]
    
    # Court patterns
    COURT_PATTERNS: Dict[str, Pattern] = {
        'federal': re.compile(r'(?:United\s+States\s+)?(?:District|Circuit|Supreme)\s+Court(?:\s+for\s+the)?\s+([^,\n]+)', re.IGNORECASE),
        'state': re.compile(r'(?:Superior|Circuit|District|Municipal|County)\s+Court\s+(?:of|for)\s+([^,\n]+)', re.IGNORECASE),
        'judge': re.compile(r'(?:Honorable|Hon\.?|Judge)\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)', re.IGNORECASE),
    }
    
    # Legal citations
    CITATION_PATTERNS: Dict[str, Pattern] = {
        'case': re.compile(r'\b\d+\s+[A-Z][a-z]+\.?\s*(?:2d|3d|4th)?\s+\d+(?:\s*\(\d{4}\))?', re.IGNORECASE),
        'statute': re.compile(r'\b\d+\s+U\.?S\.?C\.?\s+§+\s*\d+[a-z]?(?:\(\w+\))?', re.IGNORECASE),
        'federal_rule': re.compile(r'(?:Fed\.?\s*R\.?\s*(?:Civ|Crim|App|Evid)\.?\s*P\.?|FRCP|FRE)\s+\d+[a-z]?', re.IGNORECASE),
        'regulation': re.compile(r'\b\d+\s+C\.?F\.?R\.?\s+§?\s*\d+\.?\d*', re.IGNORECASE),
    }
    
    # Document type indicators
    DOCUMENT_TYPE_INDICATORS: Dict[str, List[str]] = {
        'complaint': ['COMPLAINT', 'PETITION', 'INITIAL PLEADING'],
        'answer': ['ANSWER', 'RESPONSE', 'REPLY'],
        'motion': ['MOTION', 'MOVE', 'REQUEST'],
        'brief': ['BRIEF', 'MEMORANDUM', 'MEMO'],
        'order': ['ORDER', 'ORDERED', 'IT IS HEREBY ORDERED'],
        'judgment': ['JUDGMENT', 'DECREE', 'VERDICT'],
    }
    
    # Relief/damages patterns
    RELIEF_PATTERNS: Dict[str, Pattern] = {
        'monetary': re.compile(r'\$[\d,]+(?:\.\d{2})?|\b\d+(?:,\d{3})*(?:\.\d{2})?\s+dollars', re.IGNORECASE),
        'injunction': re.compile(r'(?:preliminary|permanent|temporary)\s+(?:injunction|restraining\s+order)', re.IGNORECASE),
        'declaratory': re.compile(r'declaratory\s+(?:judgment|relief)', re.IGNORECASE),
    }
    
    @classmethod
    def extract_case_number(cls, text: str) -> Optional[str]:
        """Extract case number from text."""
        for pattern in cls.CASE_NUMBER_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(0) if match.lastindex is None else match.group(1)
        return None
    
    @classmethod
    def extract_dates(cls, text: str) -> List[Tuple[str, datetime]]:
        """Extract dates from text and parse them."""
        dates = []
        for pattern in cls.DATE_PATTERNS:
            for match in pattern.finditer(text):
                try:
                    date_str = match.group(0)
                    # Parse the date based on the format
                    if '/' in date_str or '-' in date_str:
                        # MM/DD/YYYY or MM-DD-YYYY format
                        parts = re.split(r'[/\-]', date_str)
                        if len(parts) == 3:
                            month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                            parsed_date = datetime(year, month, day)
                            dates.append((date_str, parsed_date))
                except (ValueError, IndexError):
                    continue
        return dates
    
    @classmethod
    def extract_parties(cls, text: str) -> Dict[str, List[str]]:
        """Extract party names from text."""
        parties = {'plaintiffs': [], 'defendants': []}
        
        # Try versus pattern first
        versus_match = cls.PARTY_PATTERNS['versus'].search(text)
        if versus_match:
            parties['plaintiffs'].append(versus_match.group(1).strip())
            parties['defendants'].append(versus_match.group(2).strip())
        
        # Then try specific patterns
        for match in cls.PARTY_PATTERNS['plaintiff'].finditer(text):
            party = match.group(1).strip()
            if party and party not in parties['plaintiffs']:
                parties['plaintiffs'].append(party)
        
        for match in cls.PARTY_PATTERNS['defendant'].finditer(text):
            party = match.group(1).strip()
            if party and party not in parties['defendants']:
                parties['defendants'].append(party)
        
        return parties
    
    @classmethod
    def extract_attorneys(cls, text: str) -> List[str]:
        """Extract attorney names from text."""
        attorneys = []
        for pattern in cls.ATTORNEY_PATTERNS:
            for match in pattern.finditer(text):
                attorney = match.group(1) if match.lastindex else match.group(0)
                attorney = attorney.strip()
                if attorney and attorney not in attorneys:
                    attorneys.append(attorney)
        return attorneys
    
    @classmethod
    def extract_court_info(cls, text: str) -> Dict[str, Optional[str]]:
        """Extract court information from text."""
        court_info = {'court': None, 'jurisdiction': None, 'judge': None}
        
        # Check federal courts
        federal_match = cls.COURT_PATTERNS['federal'].search(text)
        if federal_match:
            court_info['court'] = federal_match.group(0)
            court_info['jurisdiction'] = 'federal'
        
        # Check state courts
        state_match = cls.COURT_PATTERNS['state'].search(text)
        if state_match and not court_info['court']:
            court_info['court'] = state_match.group(0)
            court_info['jurisdiction'] = 'state'
        
        # Extract judge
        judge_match = cls.COURT_PATTERNS['judge'].search(text)
        if judge_match:
            court_info['judge'] = judge_match.group(1).strip()
        
        return court_info
    
    @classmethod
    def extract_citations(cls, text: str) -> Dict[str, List[str]]:
        """Extract legal citations from text."""
        citations = {
            'cases': [],
            'statutes': [],
            'rules': [],
            'regulations': []
        }
        
        for match in cls.CITATION_PATTERNS['case'].finditer(text):
            citation = match.group(0)
            if citation not in citations['cases']:
                citations['cases'].append(citation)
        
        for match in cls.CITATION_PATTERNS['statute'].finditer(text):
            citation = match.group(0)
            if citation not in citations['statutes']:
                citations['statutes'].append(citation)
        
        for match in cls.CITATION_PATTERNS['federal_rule'].finditer(text):
            citation = match.group(0)
            if citation not in citations['rules']:
                citations['rules'].append(citation)
        
        for match in cls.CITATION_PATTERNS['regulation'].finditer(text):
            citation = match.group(0)
            if citation not in citations['regulations']:
                citations['regulations'].append(citation)
        
        return citations
    
    @classmethod
    def detect_document_type(cls, text: str) -> Optional[str]:
        """Detect the type of legal document."""
        text_upper = text.upper()
        
        for doc_type, indicators in cls.DOCUMENT_TYPE_INDICATORS.items():
            for indicator in indicators:
                if indicator in text_upper[:1000]:  # Check first 1000 chars
                    return doc_type
        
        return None
    
    @classmethod
    def extract_monetary_amounts(cls, text: str) -> List[float]:
        """Extract monetary amounts from text."""
        amounts = []
        for match in cls.RELIEF_PATTERNS['monetary'].finditer(text):
            amount_str = match.group(0)
            # Clean and convert to float
            amount_str = amount_str.replace('$', '').replace(',', '').replace(' dollars', '')
            try:
                amount = float(amount_str)
                if amount not in amounts:
                    amounts.append(amount)
            except ValueError:
                continue
        return amounts