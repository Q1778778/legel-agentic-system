"""GraphRAG hybrid retrieval system - copied and adapted for lawyer server."""

from typing import List, Dict, Any, Optional
import time
import random
from datetime import datetime, timedelta
import hashlib


class GraphRAGRetrieval:
    """Simplified GraphRAG retrieval system for the lawyer server."""
    
    def __init__(self):
        """Initialize GraphRAG retrieval system."""
        # Scoring weights
        self.alpha = 0.4  # Vector similarity weight
        self.beta = 0.2   # Judge alignment weight
        self.gamma = 0.2  # Citation overlap weight
        self.delta = 0.1  # Outcome similarity weight
        self.epsilon = 0.1  # Graph distance penalty
        
    async def retrieve_past_defenses(
        self,
        issue_text: str,
        lawyer_id: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve past defense arguments using GraphRAG.
        
        Args:
            issue_text: Query text describing the legal issue
            lawyer_id: Optional lawyer filter
            jurisdiction: Optional jurisdiction filter
            limit: Maximum results
            
        Returns:
            List of relevant argument bundles
        """
        start_time = time.time()
        
        try:
            # For now, generate enhanced mock data
            # In production, this would query vector and graph databases
            bundles = self._generate_mock_bundles(issue_text, limit)
            
            query_time_ms = int((time.time() - start_time) * 1000)
            
            return bundles
            
        except Exception as e:
            print(f"Error in GraphRAG retrieval: {e}")
            return self._generate_mock_bundles(issue_text, limit)
    
    def _generate_mock_bundles(self, issue_text: str, limit: int) -> List[Dict[str, Any]]:
        """Generate enhanced mock data for demo purposes.
        
        Args:
            issue_text: User's search query text
            limit: Number of results to return
            
        Returns:
            List of mock argument bundles
        """
        mock_bundles = []
        
        # Generate relevant mock cases based on issue_text
        if "patent" in issue_text.lower() or "intellectual" in issue_text.lower():
            templates = [
                {
                    "caption": "Apple Inc. v. Samsung Electronics",
                    "court": "U.S. District Court, N.D. California",
                    "issue_title": "Design Patent Infringement",
                    "segments": [
                        {
                            "text": "The defendant's product design directly infringes our client's registered design patents, including rounded corners and icon grid layout.",
                            "role": "opening"
                        },
                        {
                            "text": "Under 35 U.S.C. § 289, any person who manufactures or sells an infringing product shall be liable for damages.",
                            "role": "response"
                        }
                    ],
                    "outcome": "granted"
                },
                {
                    "caption": "Oracle America Inc. v. Google LLC",
                    "court": "Supreme Court of the United States",
                    "issue_title": "API Copyright and Fair Use",
                    "segments": [
                        {
                            "text": "The reimplementation of Java APIs constitutes fair use under copyright law due to its transformative nature.",
                            "role": "opening"
                        },
                        {
                            "text": "APIs serve a fundamentally different purpose from creative works and should receive limited copyright protection.",
                            "role": "rebuttal"
                        }
                    ],
                    "outcome": "denied"
                }
            ]
        elif "contract" in issue_text.lower() or "breach" in issue_text.lower():
            templates = [
                {
                    "caption": "AWS v. Enterprise Client",
                    "court": "U.S. District Court, W.D. Washington",
                    "issue_title": "Service Level Agreement Breach",
                    "segments": [
                        {
                            "text": "The service outages exceeded the maximum downtime permitted under the Service Level Agreement.",
                            "role": "opening"
                        },
                        {
                            "text": "The limitation of liability clause is unconscionable given the critical nature of the services provided.",
                            "role": "response"
                        }
                    ],
                    "outcome": "partial"
                },
                {
                    "caption": "Construction Corp v. Developer LLC",
                    "court": "New York State Supreme Court",
                    "issue_title": "Construction Delay Damages",
                    "segments": [
                        {
                            "text": "Weather conditions and permit delays constitute excusable delays under the force majeure clause.",
                            "role": "opening"
                        },
                        {
                            "text": "The liquidated damages provision is unenforceable as it constitutes a penalty rather than reasonable compensation.",
                            "role": "rebuttal"
                        }
                    ],
                    "outcome": "granted"
                }
            ]
        elif "employment" in issue_text.lower() or "discrimination" in issue_text.lower():
            templates = [
                {
                    "caption": "Employee v. Tech Corporation",
                    "court": "California Superior Court",
                    "issue_title": "Wrongful Termination",
                    "segments": [
                        {
                            "text": "The termination was retaliatory following the plaintiff's whistleblower complaint to HR.",
                            "role": "opening"
                        },
                        {
                            "text": "The temporal proximity between the complaint and termination establishes a prima facie case of retaliation.",
                            "role": "response"
                        }
                    ],
                    "outcome": "granted"
                },
                {
                    "caption": "Manager v. Financial Services Inc.",
                    "court": "S.D.N.Y.",
                    "issue_title": "Age Discrimination",
                    "segments": [
                        {
                            "text": "The company's restructuring disproportionately affected employees over 50, evidencing discriminatory intent.",
                            "role": "opening"
                        },
                        {
                            "text": "Statistical evidence shows a pattern of age-based employment decisions violating the ADEA.",
                            "role": "rebuttal"
                        }
                    ],
                    "outcome": "partial"
                }
            ]
        else:
            # Default general cases
            templates = [
                {
                    "caption": "Plaintiff v. Defendant Corp",
                    "court": "Superior Court",
                    "issue_title": "General Civil Dispute",
                    "segments": [
                        {
                            "text": "The plaintiff has established a prima facie case through documentary evidence and witness testimony.",
                            "role": "opening"
                        },
                        {
                            "text": "The defendant's affirmative defenses lack supporting evidence and legal merit.",
                            "role": "response"
                        }
                    ],
                    "outcome": "granted"
                }
            ]
        
        # Generate bundles from templates
        for i, template in enumerate(templates[:limit]):
            if i >= limit:
                break
                
            bundle = {
                "argument_id": f"arg_{hashlib.md5(template['caption'].encode()).hexdigest()[:8]}",
                "confidence": {
                    "value": random.uniform(0.75, 0.95),
                    "features": {
                        "vector_similarity": random.uniform(0.7, 0.9),
                        "graph_relevance": random.uniform(0.6, 0.8),
                        "judge_alignment": random.uniform(0.65, 0.85),
                        "citation_strength": random.uniform(0.6, 0.9),
                        "outcome_similarity": random.uniform(0.7, 0.95)
                    }
                },
                "case": {
                    "id": f"case_{i:03d}",
                    "caption": template["caption"],
                    "court": template["court"],
                    "jurisdiction": "US",
                    "filed_date": (datetime.now() - timedelta(days=random.randint(30, 365))).isoformat()
                },
                "issue": {
                    "id": f"issue_{i:03d}",
                    "title": template["issue_title"],
                    "taxonomy_path": ["Law", "Civil", template["issue_title"]]
                },
                "segments": template["segments"],
                "metadata": {
                    "outcome": template["outcome"],
                    "judge": f"Judge {random.choice(['Chen', 'Smith', 'Johnson', 'Williams'])}",
                    "lawyer_id": f"lawyer_{random.randint(1, 100):03d}"
                }
            }
            mock_bundles.append(bundle)
        
        return mock_bundles
    
    def _calculate_judge_alignment_score(
        self,
        result: Dict[str, Any],
        judge_name: Optional[str] = None
    ) -> float:
        """Calculate judge alignment score."""
        # In production, this would check historical judge decisions
        return random.uniform(0.6, 0.9)
    
    def _calculate_citation_score(self, result: Dict[str, Any]) -> float:
        """Calculate citation overlap score."""
        citations = result.get("citations", [])
        return min(len(citations) / 10, 1.0)  # Normalize to 0-1
    
    def _calculate_outcome_score(self, result: Dict[str, Any]) -> float:
        """Calculate outcome similarity score."""
        outcome = result.get("metadata", {}).get("outcome", "")
        if outcome == "granted":
            return 1.0
        elif outcome == "partial":
            return 0.5
        return 0.0