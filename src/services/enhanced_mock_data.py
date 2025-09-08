"""Enhanced mock data generator with real legal cases and intelligent matching."""

from typing import List, Dict, Any, Optional
import random
from datetime import datetime, timedelta
import structlog
from .real_legal_cases_data import RealLegalCasesDatabase

logger = structlog.get_logger()

class EnhancedMockDataGenerator:
    """Generate realistic mock legal data based on actual cases."""
    
    def __init__(self):
        """Initialize with comprehensive legal case database."""
        self.db = RealLegalCasesDatabase()
        self.legal_cases = self._load_legal_cases()
    
    def _load_legal_cases(self) -> Dict[str, List[Dict]]:
        """Load comprehensive legal case database from real cases."""
        # Transform real cases into the format needed for argument generation
        transformed_cases = {
            "intellectual_property": [],
            "contract_breach": [],
            "employment": [],
            "corporate_litigation": []
        }
        
        # Process intellectual property cases
        for case in self.db.get_intellectual_property_cases()[:5]:  # Get first 5 for each category as examples
            transformed_case = {
                "caption": case["caption"],
                "court": case["court"],
                "citation": case["citation"],
                "issue_title": case["issue_title"],
                "segments": case["plaintiff_arguments"],
                "defense_segments": case["defendant_arguments"],
                "outcome": case["outcome"],
                "year": case["year"]
            }
            transformed_cases["intellectual_property"].append(transformed_case)
        
        # Process contract breach cases
        for case in self.db.get_contract_breach_cases()[:5]:
            transformed_case = {
                "caption": case["caption"],
                "court": case["court"],
                "citation": case["citation"],
                "issue_title": case["issue_title"],
                "segments": case["plaintiff_arguments"],
                "defense_segments": case["defendant_arguments"],
                "outcome": case["outcome"],
                "year": case["year"]
            }
            transformed_cases["contract_breach"].append(transformed_case)
        
        # Process employment law cases
        for case in self.db.get_employment_law_cases()[:5]:
            transformed_case = {
                "caption": case["caption"],
                "court": case["court"],
                "citation": case["citation"],
                "issue_title": case["issue_title"],
                "segments": case["plaintiff_arguments"],
                "defense_segments": case["defendant_arguments"],
                "outcome": case["outcome"],
                "year": case["year"]
            }
            transformed_cases["employment"].append(transformed_case)
        
        # Process corporate litigation cases
        for case in self.db.get_corporate_litigation_cases()[:5]:
            transformed_case = {
                "caption": case["caption"],
                "court": case["court"],
                "citation": case["citation"],
                "issue_title": case["issue_title"],
                "segments": case["plaintiff_arguments"],
                "defense_segments": case["defendant_arguments"],
                "outcome": case["outcome"],
                "year": case["year"]
            }
            transformed_cases["corporate_litigation"].append(transformed_case)
        
        return transformed_cases
    
    def analyze_user_query(self, query: str) -> str:
        """Analyze user query to determine the best matching legal category."""
        query_lower = query.lower()
        
        # Keywords for each category
        category_keywords = {
            "intellectual_property": ["patent", "copyright", "trademark", "ip", "intellectual property", 
                                    "design", "infringement", "api", "software", "technology", "trade secret"],
            "contract_breach": ["contract", "breach", "agreement", "performance", "damages", "terminated",
                              "violation", "covenant", "warranty", "indemnity", "force majeure"],
            "employment": ["employment", "discrimination", "harassment", "wrongful termination", "hostile",
                         "retaliation", "whistleblower", "wage", "hour", "ada", "disability", "bias"],
            "criminal_defense": ["criminal", "defense", "prosecution", "murder", "assault", "fraud",
                               "conspiracy", "constitutional", "miranda", "evidence", "jury"],
            "corporate_litigation": ["merger", "acquisition", "antitrust", "monopoly", "corporate",
                                   "shareholder", "fiduciary", "securities", "insider", "takeover"]
        }
        
        # Score each category
        scores = {}
        for category, keywords in category_keywords.items():
            score = sum(1 for keyword in keywords if keyword in query_lower)
            if score > 0:
                scores[category] = score
        
        # Return the category with highest score, or default to contract_breach
        if scores:
            return max(scores, key=scores.get)
        return "contract_breach"  # Default category
    
    def get_all_cases_for_category(self, category: str) -> List[Dict[str, Any]]:
        """Get all real cases for a specific category from the database."""
        if category == "intellectual_property":
            return self.db.get_intellectual_property_cases()
        elif category == "contract_breach":
            return self.db.get_contract_breach_cases()
        elif category == "employment":
            return self.db.get_employment_law_cases()
        elif category == "corporate_litigation":
            return self.db.get_corporate_litigation_cases()
        else:
            # Return a mix if category not recognized
            all_cases = []
            all_cases.extend(self.db.get_intellectual_property_cases()[:5])
            all_cases.extend(self.db.get_contract_breach_cases()[:5])
            all_cases.extend(self.db.get_employment_law_cases()[:5])
            all_cases.extend(self.db.get_corporate_litigation_cases()[:5])
            return all_cases
    
    def get_relevant_cases(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get cases relevant to the user's query."""
        category = self.analyze_user_query(query)
        
        # Get all cases for the category from the database
        all_category_cases = self.get_all_cases_for_category(category)
        
        # Transform them to the expected format
        transformed_cases = []
        for case in all_category_cases[:limit]:
            transformed_case = {
                "caption": case["caption"],
                "court": case["court"],
                "citation": case["citation"],
                "issue_title": case["issue_title"],
                "segments": case["plaintiff_arguments"],
                "defense_segments": case["defendant_arguments"],
                "outcome": case["outcome"],
                "year": case["year"]
            }
            transformed_cases.append(transformed_case)
        
        # Randomize order to provide variety
        random.shuffle(transformed_cases)
        return transformed_cases
    
    def generate_argument_bundles(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Generate enhanced argument bundles based on user query."""
        relevant_cases = self.get_relevant_cases(query, limit)
        bundles = []
        
        for i, case_data in enumerate(relevant_cases):
            case_id = f"case_{i:03d}"
            
            # Combine plaintiff and defense arguments for variety
            all_segments = case_data.get("segments", [])
            if "defense_segments" in case_data:
                # Mix plaintiff and defense arguments
                segments = []
                for j in range(min(3, len(all_segments))):
                    segments.append({
                        "text": all_segments[j],
                        "role": "plaintiff",
                        "party": "Plaintiff"
                    })
                for j in range(min(2, len(case_data["defense_segments"]))):
                    segments.append({
                        "text": case_data["defense_segments"][j],
                        "role": "defendant", 
                        "party": "Defendant"
                    })
            else:
                segments = [{"text": seg, "role": "argument", "party": "Party"} for seg in all_segments]
            
            bundle = {
                "argument_id": f"arg_{i:03d}",
                "confidence": {
                    "value": random.uniform(0.75, 0.95),
                    "features": {
                        "vector_similarity": random.uniform(0.7, 0.95),
                        "graph_relevance": random.uniform(0.6, 0.85),
                        "legal_relevance": random.uniform(0.8, 0.95)
                    }
                },
                "case": {
                    "id": case_id,
                    "caption": case_data["caption"],
                    "court": case_data["court"],
                    "citation": case_data.get("citation", ""),
                    "jurisdiction": "United States",
                    "filed_date": datetime.now() - timedelta(days=random.randint(180, 1825)),
                    "year": case_data.get("year", 2020)
                },
                "issue": {
                    "id": f"issue_{i:03d}",
                    "title": case_data["issue_title"],
                    "category": self.analyze_user_query(query).replace("_", " ").title(),
                    "taxonomy_path": ["Law", self.analyze_user_query(query).replace("_", " ").title(), 
                                    case_data["issue_title"][:50]]
                },
                "segments": [
                    {
                        "segment_id": f"seg_{case_id}_{j:02d}",
                        "argument_id": f"arg_{i:03d}",
                        "text": seg["text"],
                        "role": seg["role"],
                        "party": seg["party"],
                        "seq": j,
                        "citations": self._extract_citations(seg["text"])
                    }
                    for j, seg in enumerate(segments)
                ],
                "metadata": {
                    "outcome": case_data.get("outcome", "Pending"),
                    "judge": f"Judge {random.choice(['Chen', 'Gonzalez', 'Koh', 'Alsup', 'Davila'])}",
                    "category": self.analyze_user_query(query),
                    "relevance_score": random.uniform(0.8, 1.0)
                }
            }
            bundles.append(bundle)
        
        return bundles
    
    def _extract_citations(self, text: str) -> List[str]:
        """Extract legal citations from text."""
        import re
        
        citations = []
        
        # U.S. Code citations (e.g., "42 U.S.C. § 1983")
        usc_pattern = r'\d+\s+U\.S\.C\.\s+§\s+\d+'
        citations.extend(re.findall(usc_pattern, text))
        
        # Federal Reporter citations (e.g., "123 F.3d 456")
        fed_pattern = r'\d+\s+F\.\d+d\s+\d+'
        citations.extend(re.findall(fed_pattern, text))
        
        # Case law citations (e.g., "Griggs v. Duke Power")
        case_pattern = r'[A-Z][a-z]+\s+v\.\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*'
        citations.extend(re.findall(case_pattern, text))
        
        return citations[:3] if citations else ["Federal Rules of Civil Procedure"]

# Singleton instance
_generator = None

def get_generator() -> EnhancedMockDataGenerator:
    """Get singleton instance of the generator."""
    global _generator
    if _generator is None:
        _generator = EnhancedMockDataGenerator()
    return _generator