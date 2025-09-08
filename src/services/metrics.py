"""
Core Metrics Service for Court Argument Simulator
Implements the metrics from PDF specification
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict
import hashlib
from src.db.graph_db import GraphDB
from src.models.schemas import ArgumentBundle

class MetricsService:
    """
    Service for calculating core metrics as specified in the PDF:
    1. Win Rate / Outcome Success
    2. Judge Alignment Rate  
    3. Argument Diversity
    """
    
    def __init__(self):
        self.graph_db = GraphDB()
        # Get the Neo4j driver directly
        self.driver = self.graph_db.driver
    
    def calculate_win_rate(
        self, 
        lawyer_id: Optional[str] = None,
        issue_id: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        judge_name: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Calculate Win Rate / Outcome Success
        Formula: (granted + 0.5*partial) / total
        Scope: per issue, per jurisdiction, per judge
        """
        query = """
        MATCH (l:Lawyer)-[:ARGUED]->(a:Argument)-[:ARGUED_IN]->(c:Case)
        OPTIONAL MATCH (c)-[:ADDRESSES]->(i:Issue)
        OPTIONAL MATCH (c)-[:HEARD_BY]->(j:Judge)
        WHERE 1=1
        """
        
        parameters = {}
        
        if lawyer_id:
            query += " AND l.id = $lawyer_id"
            parameters["lawyer_id"] = lawyer_id
        
        if issue_id:
            query += " AND i.id = $issue_id"
            parameters["issue_id"] = issue_id
            
        if jurisdiction:
            query += " AND c.jurisdiction = $jurisdiction"
            parameters["jurisdiction"] = jurisdiction
            
        if judge_name:
            query += " AND j.name = $judge_name"
            parameters["judge_name"] = judge_name
        
        query += """
        RETURN 
            l.id as lawyer_id,
            i.id as issue_id,
            c.jurisdiction as jurisdiction,
            j.name as judge_name,
            a.outcome as outcome
        """
        
        with self.driver.session() as session:
            results = session.run(query, **parameters).data()
        
        # Calculate metrics
        outcomes = defaultdict(lambda: {"granted": 0, "partial": 0, "total": 0})
        
        for record in results:
            key = (
                record.get("lawyer_id", "unknown"),
                record.get("issue_id", "unknown"),
                record.get("jurisdiction", "unknown"),
                record.get("judge_name", "unknown")
            )
            
            outcome = record.get("outcome", "").lower()
            outcomes[key]["total"] += 1
            
            if outcome == "won" or outcome == "granted":
                outcomes[key]["granted"] += 1
            elif outcome == "partial" or outcome == "settled":
                outcomes[key]["partial"] += 1
        
        # Calculate win rates
        win_rates = {}
        for key, counts in outcomes.items():
            if counts["total"] > 0:
                win_rate = (counts["granted"] + 0.5 * counts["partial"]) / counts["total"]
                win_rates[f"{key[0]}_{key[1]}_{key[2]}_{key[3]}"] = {
                    "win_rate": win_rate,
                    "total_cases": counts["total"],
                    "granted": counts["granted"],
                    "partial": counts["partial"],
                    "lawyer_id": key[0],
                    "issue_id": key[1],
                    "jurisdiction": key[2],
                    "judge": key[3]
                }
        
        # Calculate overall win rate if multiple results
        if win_rates:
            total_granted = sum(v["granted"] for v in win_rates.values())
            total_partial = sum(v["partial"] for v in win_rates.values())
            total_cases = sum(v["total_cases"] for v in win_rates.values())
            
            if total_cases > 0:
                overall_win_rate = (total_granted + 0.5 * total_partial) / total_cases
            else:
                overall_win_rate = 0.0
            
            return {
                "overall_win_rate": overall_win_rate,
                "total_cases": total_cases,
                "breakdown": win_rates
            }
        
        return {
            "overall_win_rate": 0.0,
            "total_cases": 0,
            "breakdown": {}
        }
    
    def calculate_judge_alignment_rate(
        self,
        lawyer_id: str,
        judge_name: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Calculate Judge Alignment Rate
        Formula: aligned_outcomes / total_appearances_before_judge
        "Aligned" = outcome disposition matches the lawyer's requested ruling
        """
        query = """
        MATCH (l:Lawyer {id: $lawyer_id})-[:ARGUED]->(a:Argument)-[:ARGUED_IN]->(c:Case)
        MATCH (c)-[:HEARD_BY]->(j:Judge)
        """
        
        parameters = {"lawyer_id": lawyer_id}
        
        if judge_name:
            query += " WHERE j.name = $judge_name"
            parameters["judge_name"] = judge_name
        
        query += """
        RETURN 
            j.name as judge_name,
            a.outcome as outcome,
            a.requested_ruling as requested_ruling
        """
        
        with self.driver.session() as session:
            results = session.run(query, **parameters).data()
        
        # Calculate alignment by judge
        alignment_by_judge = defaultdict(lambda: {"aligned": 0, "total": 0})
        
        for record in results:
            judge = record.get("judge_name", "unknown")
            outcome = record.get("outcome", "").lower()
            requested = record.get("requested_ruling", "granted").lower()
            
            alignment_by_judge[judge]["total"] += 1
            
            # Check if outcome aligns with requested ruling
            if self._outcomes_aligned(outcome, requested):
                alignment_by_judge[judge]["aligned"] += 1
        
        # Calculate alignment rates
        alignment_rates = {}
        total_aligned = 0
        total_appearances = 0
        
        for judge, counts in alignment_by_judge.items():
            if counts["total"] > 0:
                rate = counts["aligned"] / counts["total"]
                alignment_rates[judge] = {
                    "alignment_rate": rate,
                    "aligned_cases": counts["aligned"],
                    "total_appearances": counts["total"]
                }
                total_aligned += counts["aligned"]
                total_appearances += counts["total"]
        
        # Calculate overall alignment rate
        overall_rate = total_aligned / total_appearances if total_appearances > 0 else 0.0
        
        return {
            "lawyer_id": lawyer_id,
            "overall_alignment_rate": overall_rate,
            "total_appearances": total_appearances,
            "by_judge": alignment_rates
        }
    
    def calculate_argument_diversity(
        self,
        lawyer_id: Optional[str] = None,
        issue_id: Optional[str] = None,
        jurisdiction: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Calculate Argument Diversity
        Formula: countDistinct(signature_hash)
        Proxy for variety of legal strategies
        """
        query = """
        MATCH (l:Lawyer)-[:ARGUED]->(a:Argument)
        OPTIONAL MATCH (a)-[:ARGUED_IN]->(c:Case)
        OPTIONAL MATCH (c)-[:ADDRESSES]->(i:Issue)
        WHERE 1=1
        """
        
        parameters = {}
        
        if lawyer_id:
            query += " AND l.id = $lawyer_id"
            parameters["lawyer_id"] = lawyer_id
        
        if issue_id:
            query += " AND i.id = $issue_id"
            parameters["issue_id"] = issue_id
        
        if jurisdiction:
            query += " AND c.jurisdiction = $jurisdiction"
            parameters["jurisdiction"] = jurisdiction
        
        query += """
        RETURN DISTINCT
            l.id as lawyer_id,
            a.signature_hash as signature_hash,
            a.strategy_type as strategy_type
        """
        
        with self.driver.session() as session:
            results = session.run(query, **parameters).data()
        
        # Count unique signatures
        unique_signatures = set()
        strategy_types = defaultdict(int)
        lawyers_signatures = defaultdict(set)
        
        for record in results:
            sig_hash = record.get("signature_hash")
            strategy = record.get("strategy_type", "unknown")
            lawyer = record.get("lawyer_id", "unknown")
            
            if sig_hash:
                unique_signatures.add(sig_hash)
                lawyers_signatures[lawyer].add(sig_hash)
            
            strategy_types[strategy] += 1
        
        # Calculate diversity metrics
        diversity_metrics = {
            "total_unique_arguments": len(unique_signatures),
            "strategy_distribution": dict(strategy_types),
            "scope": {
                "lawyer_id": lawyer_id,
                "issue_id": issue_id,
                "jurisdiction": jurisdiction
            }
        }
        
        # Add per-lawyer diversity if not filtered by lawyer
        if not lawyer_id:
            diversity_metrics["by_lawyer"] = {
                lawyer: len(sigs) for lawyer, sigs in lawyers_signatures.items()
            }
        
        return diversity_metrics
    
    def _outcomes_aligned(self, outcome: str, requested: str) -> bool:
        """Check if outcome aligns with requested ruling"""
        positive_outcomes = {"won", "granted", "approved"}
        negative_outcomes = {"lost", "denied", "rejected"}
        partial_outcomes = {"partial", "settled", "modified"}
        
        if outcome in positive_outcomes and requested in positive_outcomes:
            return True
        if outcome in negative_outcomes and requested in negative_outcomes:
            return True
        if outcome in partial_outcomes and requested in partial_outcomes:
            return True
        
        return False
    
    def generate_argument_signature(self, argument_text: str, citations: List[str]) -> str:
        """
        Generate a signature hash for an argument
        Used for diversity calculation
        """
        # Combine text and citations to create signature
        signature_input = argument_text.lower().strip()
        signature_input += "".join(sorted(citations))
        
        # Create hash
        return hashlib.sha256(signature_input.encode()).hexdigest()
    
    def get_comprehensive_metrics(
        self,
        lawyer_id: Optional[str] = None,
        issue_id: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        judge_name: Optional[str] = None
    ) -> Dict:
        """
        Get all core metrics in one call
        """
        metrics = {}
        
        # Win Rate
        metrics["win_rate"] = self.calculate_win_rate(
            lawyer_id=lawyer_id,
            issue_id=issue_id,
            jurisdiction=jurisdiction,
            judge_name=judge_name
        )
        
        # Judge Alignment (only if lawyer_id provided)
        if lawyer_id:
            metrics["judge_alignment"] = self.calculate_judge_alignment_rate(
                lawyer_id=lawyer_id,
                judge_name=judge_name
            )
        
        # Argument Diversity
        metrics["argument_diversity"] = self.calculate_argument_diversity(
            lawyer_id=lawyer_id,
            issue_id=issue_id,
            jurisdiction=jurisdiction
        )
        
        # Add metadata
        metrics["metadata"] = {
            "calculated_at": datetime.now().isoformat(),
            "filters": {
                "lawyer_id": lawyer_id,
                "issue_id": issue_id,
                "jurisdiction": jurisdiction,
                "judge_name": judge_name
            }
        }
        
        return metrics