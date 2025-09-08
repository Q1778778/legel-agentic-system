"""
Validation logic for extracted case information.

This module provides validation functions to ensure data quality
and completeness before sending to downstream services.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import re

from .models import (
    ExtractedCaseInfo, 
    Party, 
    CourtInfo, 
    LegalIssue,
    CaseType,
    CaseStage,
    PartyType
)


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


class CaseInfoValidator:
    """Validator for extracted case information."""
    
    # Required fields for different contexts
    REQUIRED_FIELDS = {
        'minimal': ['case_title'],  # Absolute minimum
        'basic': ['case_number', 'case_title', 'case_type'],
        'standard': ['case_number', 'case_title', 'case_type', 'parties', 'court_info'],
        'complete': [
            'case_number', 'case_title', 'filing_date', 'case_type', 
            'case_stage', 'parties', 'court_info', 'legal_issues'
        ]
    }
    
    # Field-specific validation rules
    FIELD_VALIDATORS = {
        'case_number': lambda x: bool(x and re.match(r'^[\w\-\/]+$', x)),
        'case_title': lambda x: bool(x and len(x) > 3),
        'filing_date': lambda x: isinstance(x, datetime) and x <= datetime.utcnow(),
        'confidence_score': lambda x: 0.0 <= x <= 1.0,
    }
    
    @classmethod
    def validate(
        cls, 
        case_info: ExtractedCaseInfo, 
        validation_level: str = 'standard',
        raise_on_error: bool = False
    ) -> Tuple[bool, List[str]]:
        """
        Validate extracted case information.
        
        Args:
            case_info: The extracted case information to validate
            validation_level: Level of validation ('minimal', 'basic', 'standard', 'complete')
            raise_on_error: Whether to raise exception on validation failure
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check required fields
        required_fields = cls.REQUIRED_FIELDS.get(validation_level, cls.REQUIRED_FIELDS['standard'])
        for field in required_fields:
            value = getattr(case_info, field, None)
            if value is None or (isinstance(value, (list, dict)) and len(value) == 0):
                errors.append(f"Required field '{field}' is missing or empty")
        
        # Validate case number format
        if case_info.case_number:
            if not cls.FIELD_VALIDATORS['case_number'](case_info.case_number):
                errors.append(f"Invalid case number format: {case_info.case_number}")
        
        # Validate case title
        if case_info.case_title:
            if not cls.FIELD_VALIDATORS['case_title'](case_info.case_title):
                errors.append(f"Invalid case title: {case_info.case_title}")
        
        # Validate filing date
        if case_info.filing_date:
            if not cls.FIELD_VALIDATORS['filing_date'](case_info.filing_date):
                errors.append(f"Invalid filing date: {case_info.filing_date}")
        
        # Validate parties
        if case_info.parties:
            errors.extend(cls._validate_parties(case_info.parties))
        
        # Validate court info
        if case_info.court_info:
            errors.extend(cls._validate_court_info(case_info.court_info))
        
        # Validate legal issues
        if case_info.legal_issues:
            errors.extend(cls._validate_legal_issues(case_info.legal_issues))
        
        # Validate confidence score
        if not cls.FIELD_VALIDATORS['confidence_score'](case_info.confidence_score):
            errors.append(f"Invalid confidence score: {case_info.confidence_score}")
        
        is_valid = len(errors) == 0
        
        if not is_valid and raise_on_error:
            raise ValidationError(f"Validation failed: {'; '.join(errors)}")
        
        return is_valid, errors
    
    @staticmethod
    def _validate_parties(parties: List[Party]) -> List[str]:
        """Validate party information."""
        errors = []
        
        if len(parties) == 0:
            errors.append("No parties found in case")
            return errors
        
        # Check for at least one plaintiff/petitioner and one defendant/respondent
        has_plaintiff = any(
            p.party_type in [PartyType.PLAINTIFF, PartyType.PETITIONER, PartyType.APPELLANT] 
            for p in parties
        )
        has_defendant = any(
            p.party_type in [PartyType.DEFENDANT, PartyType.RESPONDENT, PartyType.APPELLEE] 
            for p in parties
        )
        
        if not has_plaintiff:
            errors.append("No plaintiff/petitioner/appellant found")
        if not has_defendant:
            errors.append("No defendant/respondent/appellee found")
        
        # Validate each party
        for i, party in enumerate(parties):
            if not party.name or len(party.name) < 2:
                errors.append(f"Invalid party name at index {i}: {party.name}")
            
            if party.attorneys:
                for attorney in party.attorneys:
                    if not attorney or len(attorney) < 2:
                        errors.append(f"Invalid attorney name for party {party.name}: {attorney}")
        
        return errors
    
    @staticmethod
    def _validate_court_info(court_info: CourtInfo) -> List[str]:
        """Validate court information."""
        errors = []
        
        if not court_info.name or len(court_info.name) < 3:
            errors.append(f"Invalid court name: {court_info.name}")
        
        valid_jurisdictions = ['federal', 'state', 'local', 'administrative', 'international']
        if court_info.jurisdiction.lower() not in valid_jurisdictions:
            errors.append(f"Invalid jurisdiction: {court_info.jurisdiction}")
        
        if court_info.judge and len(court_info.judge) < 3:
            errors.append(f"Invalid judge name: {court_info.judge}")
        
        return errors
    
    @staticmethod
    def _validate_legal_issues(legal_issues: List[LegalIssue]) -> List[str]:
        """Validate legal issues."""
        errors = []
        
        if len(legal_issues) == 0:
            return errors  # Legal issues are optional in some cases
        
        # Check for at least one primary issue
        has_primary = any(issue.is_primary for issue in legal_issues)
        if not has_primary and len(legal_issues) > 0:
            errors.append("No primary legal issue identified")
        
        # Validate each issue
        for i, issue in enumerate(legal_issues):
            if not issue.issue or len(issue.issue) < 5:
                errors.append(f"Invalid legal issue description at index {i}")
            
            if not issue.category:
                errors.append(f"Missing category for legal issue at index {i}")
        
        return errors
    
    @classmethod
    def calculate_completeness_score(cls, case_info: ExtractedCaseInfo) -> float:
        """
        Calculate a completeness score for the extracted information.
        
        Returns:
            Score between 0.0 and 1.0 indicating completeness
        """
        total_fields = 0
        filled_fields = 0
        
        # Define field weights (importance)
        field_weights = {
            'case_number': 2.0,
            'case_title': 2.0,
            'filing_date': 1.5,
            'case_type': 1.5,
            'case_stage': 1.0,
            'parties': 2.0,
            'court_info': 1.5,
            'legal_issues': 1.5,
            'fact_summary': 1.0,
            'disputed_facts': 0.5,
            'relief_sought': 1.0,
            'document_references': 0.5,
        }
        
        for field, weight in field_weights.items():
            total_fields += weight
            value = getattr(case_info, field, None)
            
            if value is not None:
                if isinstance(value, list):
                    if len(value) > 0:
                        filled_fields += weight
                elif isinstance(value, str):
                    if len(value.strip()) > 0:
                        filled_fields += weight
                else:
                    filled_fields += weight
        
        return filled_fields / total_fields if total_fields > 0 else 0.0
    
    @classmethod
    def suggest_missing_fields(cls, case_info: ExtractedCaseInfo) -> List[str]:
        """
        Suggest which fields should be filled for better completeness.
        
        Returns:
            List of field names that should be filled
        """
        missing_fields = []
        
        # Priority order for fields
        priority_fields = [
            'case_number', 'case_title', 'case_type', 'filing_date',
            'parties', 'court_info', 'legal_issues', 'fact_summary',
            'relief_sought', 'case_stage'
        ]
        
        for field in priority_fields:
            value = getattr(case_info, field, None)
            if value is None or (isinstance(value, (list, dict)) and len(value) == 0):
                missing_fields.append(field)
        
        return missing_fields
    
    @classmethod
    def validate_for_integration(
        cls, 
        case_info: ExtractedCaseInfo,
        target_system: str = 'info_fetcher'
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Validate case info for specific integration target.
        
        Args:
            case_info: The extracted case information
            target_system: Target system for integration
            
        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        errors = []
        warnings = {}
        
        if target_system == 'info_fetcher':
            # Specific validation for info fetcher integration
            if not case_info.case_number and not case_info.case_title:
                errors.append("Either case_number or case_title is required for info fetcher")
            
            if not case_info.parties or len(case_info.parties) < 2:
                warnings['parties'] = "Info fetcher works best with at least 2 parties"
            
            if not case_info.legal_issues:
                warnings['legal_issues'] = "Legal issues help improve search results"
            
            if case_info.confidence_score < 0.7:
                warnings['confidence'] = f"Low confidence score: {case_info.confidence_score}"
        
        # Run standard validation
        is_valid, validation_errors = cls.validate(case_info, 'basic')
        errors.extend(validation_errors)
        
        return len(errors) == 0, errors, warnings