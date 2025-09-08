"""Graph database abstraction layer using Neo4j."""

from typing import List, Dict, Any, Optional, Tuple
from neo4j import GraphDatabase, Driver, Session
from neo4j.exceptions import Neo4jError
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
from datetime import datetime
import json

from ..core.config import settings
from ..models.schemas import (
    ArgumentBundle,
    Case,
    Lawyer,
    Judge,
    Issue,
    Citation,
)

logger = structlog.get_logger()


class GraphDB:
    """Neo4j graph database interface."""
    
    def __init__(self):
        """Initialize Neo4j driver."""
        self.driver: Driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        self.database = settings.neo4j_database
        self._ensure_constraints()
    
    def close(self):
        """Close database connection."""
        if self.driver:
            self.driver.close()
    
    def _ensure_constraints(self) -> None:
        """Ensure constraints and indexes exist."""
        constraints = [
            "CREATE CONSTRAINT issue_id IF NOT EXISTS FOR (n:Issue) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT argument_id IF NOT EXISTS FOR (n:Argument) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT segment_id IF NOT EXISTS FOR (n:Segment) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT lawyer_id IF NOT EXISTS FOR (n:Lawyer) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT judge_id IF NOT EXISTS FOR (n:Judge) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT case_id IF NOT EXISTS FOR (n:Case) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT precedent_id IF NOT EXISTS FOR (n:Precedent) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT statute_id IF NOT EXISTS FOR (n:Statute) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT court_id IF NOT EXISTS FOR (n:Court) REQUIRE n.id IS UNIQUE",
        ]
        
        indexes = [
            "CREATE INDEX issue_title IF NOT EXISTS FOR (n:Issue) ON (n.title)",
            "CREATE INDEX node_tenant IF NOT EXISTS FOR (n) ON (n.tenant)",
            "CREATE INDEX case_jurisdiction IF NOT EXISTS FOR (n:Case) ON (n.jurisdiction)",
            "CREATE INDEX case_filed_date IF NOT EXISTS FOR (n:Case) ON (n.filed_date)",
            "CREATE INDEX lawyer_name IF NOT EXISTS FOR (n:Lawyer) ON (n.name)",
            "CREATE INDEX judge_name IF NOT EXISTS FOR (n:Judge) ON (n.name)",
        ]
        
        with self.driver.session(database=self.database) as session:
            # Create constraints
            for constraint in constraints:
                try:
                    session.run(constraint)
                    logger.info(f"Created constraint: {constraint[:50]}...")
                except Neo4jError as e:
                    if "already exists" not in str(e):
                        logger.error(f"Error creating constraint: {e}")
            
            # Create indexes
            for index in indexes:
                try:
                    session.run(index)
                    logger.info(f"Created index: {index[:50]}...")
                except Neo4jError as e:
                    if "already exists" not in str(e):
                        logger.error(f"Error creating index: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def upsert_nodes_and_edges(
        self,
        bundle: ArgumentBundle,
        tenant: str = "default",
    ) -> bool:
        """Upsert nodes and relationships from argument bundle.
        
        Args:
            bundle: Argument bundle with all data
            tenant: Tenant identifier
            
        Returns:
            Success status
        """
        try:
            with self.driver.session(database=self.database) as session:
                # Upsert Lawyer node
                if bundle.lawyer:
                    session.run(
                        """
                        MERGE (l:Lawyer {id: $id, tenant: $tenant})
                        SET l.name = $name,
                            l.bar_id = $bar_id,
                            l.firm = $firm,
                            l.updated_at = datetime()
                        """,
                        id=bundle.lawyer.id,
                        name=bundle.lawyer.name,
                        bar_id=bundle.lawyer.bar_id,
                        firm=bundle.lawyer.firm,
                        tenant=tenant,
                    )
                
                # Upsert Case node
                session.run(
                    """
                    MERGE (c:Case {id: $id, tenant: $tenant})
                    SET c.caption = $caption,
                        c.court = $court,
                        c.jurisdiction = $jurisdiction,
                        c.filed_date = $filed_date,
                        c.outcome = $outcome,
                        c.updated_at = datetime()
                    """,
                    id=bundle.case.id,
                    caption=bundle.case.caption,
                    court=bundle.case.court,
                    jurisdiction=bundle.case.jurisdiction,
                    filed_date=bundle.case.filed_date.isoformat() if bundle.case.filed_date else None,
                    outcome=bundle.case.outcome,
                    tenant=tenant,
                )
                
                # Upsert Judge node if present
                if bundle.case.judge_id:
                    session.run(
                        """
                        MERGE (j:Judge {id: $id, tenant: $tenant})
                        SET j.name = $name,
                            j.updated_at = datetime()
                        """,
                        id=bundle.case.judge_id,
                        name=bundle.case.judge_name,
                        tenant=tenant,
                    )
                    
                    # Create HEARD_BY relationship
                    session.run(
                        """
                        MATCH (c:Case {id: $case_id, tenant: $tenant})
                        MATCH (j:Judge {id: $judge_id, tenant: $tenant})
                        MERGE (c)-[:HEARD_BY]->(j)
                        """,
                        case_id=bundle.case.id,
                        judge_id=bundle.case.judge_id,
                        tenant=tenant,
                    )
                
                # Upsert Issue node
                session.run(
                    """
                    MERGE (i:Issue {id: $id, tenant: $tenant})
                    SET i.title = $title,
                        i.taxonomy_path = $taxonomy_path,
                        i.updated_at = datetime()
                    """,
                    id=bundle.issue.id,
                    title=bundle.issue.title,
                    taxonomy_path=bundle.issue.taxonomy_path,
                    tenant=tenant,
                )
                
                # Upsert Argument node
                session.run(
                    """
                    MERGE (a:Argument {id: $id, tenant: $tenant})
                    SET a.stage = $stage,
                        a.disposition = $disposition,
                        a.signature_hash = $signature_hash,
                        a.confidence = $confidence,
                        a.updated_at = datetime()
                    """,
                    id=bundle.argument_id,
                    stage=bundle.stage.value if bundle.stage else None,
                    disposition=bundle.disposition.value if bundle.disposition else None,
                    signature_hash=bundle.signature_hash,
                    confidence=bundle.confidence.value,
                    tenant=tenant,
                )
                
                # Create relationships
                # Lawyer -> Argument
                if bundle.lawyer:
                    session.run(
                        """
                        MATCH (l:Lawyer {id: $lawyer_id, tenant: $tenant})
                        MATCH (a:Argument {id: $argument_id, tenant: $tenant})
                        MERGE (l)-[:ARGUED]->(a)
                        """,
                        lawyer_id=bundle.lawyer.id,
                        argument_id=bundle.argument_id,
                        tenant=tenant,
                    )
                
                # Argument -> Case
                session.run(
                    """
                    MATCH (a:Argument {id: $argument_id, tenant: $tenant})
                    MATCH (c:Case {id: $case_id, tenant: $tenant})
                    MERGE (a)-[:IN_CASE]->(c)
                    """,
                    argument_id=bundle.argument_id,
                    case_id=bundle.case.id,
                    tenant=tenant,
                )
                
                # Argument -> Issue
                session.run(
                    """
                    MATCH (a:Argument {id: $argument_id, tenant: $tenant})
                    MATCH (i:Issue {id: $issue_id, tenant: $tenant})
                    MERGE (a)-[:ADDRESSES]->(i)
                    """,
                    argument_id=bundle.argument_id,
                    issue_id=bundle.issue.id,
                    tenant=tenant,
                )
                
                # Upsert Segments
                for segment in bundle.segments:
                    session.run(
                        """
                        MERGE (s:Segment {id: $id, tenant: $tenant})
                        SET s.text = $text,
                            s.role = $role,
                            s.seq = $seq,
                            s.citations = $citations,
                            s.updated_at = datetime()
                        """,
                        id=segment.segment_id,
                        text=segment.text,
                        role=segment.role,
                        seq=segment.seq,
                        citations=segment.citations,
                        tenant=tenant,
                    )
                    
                    # Segment -> Argument
                    session.run(
                        """
                        MATCH (s:Segment {id: $segment_id, tenant: $tenant})
                        MATCH (a:Argument {id: $argument_id, tenant: $tenant})
                        MERGE (s)-[:PART_OF]->(a)
                        """,
                        segment_id=segment.segment_id,
                        argument_id=bundle.argument_id,
                        tenant=tenant,
                    )
                
                # Handle Citations
                for citation in bundle.citations:
                    if citation.type == "case":
                        node_label = "Precedent"
                    elif citation.type == "statute":
                        node_label = "Statute"
                    else:
                        node_label = "Citation"
                    
                    # Create citation node
                    session.run(
                        f"""
                        MERGE (c:{node_label} {{text: $text, tenant: $tenant}})
                        SET c.normalized = $normalized,
                            c.updated_at = datetime()
                        """,
                        text=citation.text,
                        normalized=citation.normalized,
                        tenant=tenant,
                    )
                    
                    # Argument -> Citation
                    session.run(
                        f"""
                        MATCH (a:Argument {{id: $argument_id, tenant: $tenant}})
                        MATCH (c:{node_label} {{text: $citation_text, tenant: $tenant}})
                        MERGE (a)-[:CITES]->(c)
                        """,
                        argument_id=bundle.argument_id,
                        citation_text=citation.text,
                        tenant=tenant,
                    )
                
                logger.info(f"Upserted graph nodes for argument {bundle.argument_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error upserting graph data: {e}")
            raise
    
    def expand_issues(
        self,
        issue_id: str,
        tenant: str = "default",
        max_hops: int = 2,
    ) -> List[str]:
        """Expand issue to related issues via taxonomy.
        
        Args:
            issue_id: Starting issue ID
            tenant: Tenant identifier
            max_hops: Maximum hops for expansion
            
        Returns:
            List of expanded issue IDs
        """
        try:
            with self.driver.session(database=self.database) as session:
                # Use APOC if available, otherwise manual traversal
                result = session.run(
                    """
                    MATCH (i:Issue {id: $issue_id, tenant: $tenant})
                    CALL {
                        WITH i
                        MATCH path = (i)-[:NARROWER_THAN|BROADER_THAN*0..%d]-(i2:Issue)
                        WHERE i2.tenant = $tenant
                        RETURN DISTINCT i2.id AS expanded_id
                    }
                    RETURN collect(DISTINCT expanded_id) AS expanded_ids
                    """ % max_hops,
                    issue_id=issue_id,
                    tenant=tenant,
                )
                
                record = result.single()
                if record:
                    expanded_ids = record["expanded_ids"]
                    logger.info(f"Expanded issue {issue_id} to {len(expanded_ids)} related issues")
                    return expanded_ids
                return [issue_id]
                
        except Exception as e:
            logger.error(f"Error expanding issues: {e}")
            return [issue_id]
    
    def get_subgraph_for_arguments(
        self,
        argument_ids: List[str],
        tenant: str = "default",
    ) -> Dict[str, Any]:
        """Get subgraph for given arguments.
        
        Args:
            argument_ids: List of argument IDs
            tenant: Tenant identifier
            
        Returns:
            Subgraph data with nodes and relationships
        """
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(
                    """
                    MATCH (a:Argument)
                    WHERE a.id IN $argument_ids AND a.tenant = $tenant
                    OPTIONAL MATCH (a)-[r1:IN_CASE]->(c:Case)
                    OPTIONAL MATCH (a)-[r2:ADDRESSES]->(i:Issue)
                    OPTIONAL MATCH (a)-[r3:CITES]->(cite)
                    OPTIONAL MATCH (l:Lawyer)-[r4:ARGUED]->(a)
                    OPTIONAL MATCH (c)-[r5:HEARD_BY]->(j:Judge)
                    RETURN 
                        collect(DISTINCT a) AS arguments,
                        collect(DISTINCT c) AS cases,
                        collect(DISTINCT i) AS issues,
                        collect(DISTINCT cite) AS citations,
                        collect(DISTINCT l) AS lawyers,
                        collect(DISTINCT j) AS judges,
                        collect(DISTINCT r1) + collect(DISTINCT r2) + 
                        collect(DISTINCT r3) + collect(DISTINCT r4) + 
                        collect(DISTINCT r5) AS relationships
                    """,
                    argument_ids=argument_ids,
                    tenant=tenant,
                )
                
                record = result.single()
                if record:
                    return {
                        "arguments": [dict(a) for a in record["arguments"]],
                        "cases": [dict(c) for c in record["cases"] if c],
                        "issues": [dict(i) for i in record["issues"] if i],
                        "citations": [dict(cite) for cite in record["citations"] if cite],
                        "lawyers": [dict(l) for l in record["lawyers"] if l],
                        "judges": [dict(j) for j in record["judges"] if j],
                        "relationships": len(record["relationships"]),
                    }
                return {}
                
        except Exception as e:
            logger.error(f"Error getting subgraph: {e}")
            raise
    
    def calculate_graph_boosts(
        self,
        argument_id: str,
        judge_id: Optional[str] = None,
        tenant: str = "default",
    ) -> Dict[str, float]:
        """Calculate graph-based scoring boosts.
        
        Args:
            argument_id: Argument to score
            judge_id: Optional judge for matching
            tenant: Tenant identifier
            
        Returns:
            Dictionary of boost factors
        """
        boosts = {
            "judge_match": 0.0,
            "citation_overlap": 0.0,
            "outcome_boost": 0.0,
            "issue_centrality": 0.0,
        }
        
        try:
            with self.driver.session(database=self.database) as session:
                # Check judge match
                if judge_id:
                    result = session.run(
                        """
                        MATCH (a:Argument {id: $argument_id, tenant: $tenant})-[:IN_CASE]->(c:Case)-[:HEARD_BY]->(j:Judge {id: $judge_id})
                        RETURN count(*) AS match_count
                        """,
                        argument_id=argument_id,
                        judge_id=judge_id,
                        tenant=tenant,
                    )
                    record = result.single()
                    if record and record["match_count"] > 0:
                        boosts["judge_match"] = 0.1
                
                # Calculate citation overlap (simplified)
                result = session.run(
                    """
                    MATCH (a:Argument {id: $argument_id, tenant: $tenant})-[:CITES]->(cite)
                    WITH count(DISTINCT cite) AS citation_count
                    RETURN CASE 
                        WHEN citation_count > 10 THEN 0.2
                        WHEN citation_count > 5 THEN 0.15
                        WHEN citation_count > 0 THEN 0.1
                        ELSE 0.0
                    END AS citation_boost
                    """,
                    argument_id=argument_id,
                    tenant=tenant,
                )
                record = result.single()
                if record:
                    boosts["citation_overlap"] = record["citation_boost"]
                
                # Check favorable outcome
                result = session.run(
                    """
                    MATCH (a:Argument {id: $argument_id, tenant: $tenant})
                    WHERE a.disposition IN ['granted', 'partial']
                    RETURN a.disposition AS disposition
                    """,
                    argument_id=argument_id,
                    tenant=tenant,
                )
                record = result.single()
                if record:
                    if record["disposition"] == "granted":
                        boosts["outcome_boost"] = 0.15
                    elif record["disposition"] == "partial":
                        boosts["outcome_boost"] = 0.1
                
                # Issue centrality (simplified)
                result = session.run(
                    """
                    MATCH (a:Argument {id: $argument_id, tenant: $tenant})-[:ADDRESSES]->(i:Issue)
                    MATCH (i)-[:NARROWER_THAN|BROADER_THAN]-(related:Issue)
                    RETURN count(DISTINCT related) AS related_count
                    """,
                    argument_id=argument_id,
                    tenant=tenant,
                )
                record = result.single()
                if record:
                    related_count = record["related_count"]
                    if related_count > 5:
                        boosts["issue_centrality"] = 0.1
                    elif related_count > 2:
                        boosts["issue_centrality"] = 0.05
                
                return boosts
                
        except Exception as e:
            logger.error(f"Error calculating graph boosts: {e}")
            return boosts
    
    def get_issue_hierarchy(
        self,
        issue_id: str,
        tenant: str = "default",
    ) -> Dict[str, Any]:
        """Get issue taxonomy hierarchy.
        
        Args:
            issue_id: Issue ID
            tenant: Tenant identifier
            
        Returns:
            Issue hierarchy data
        """
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(
                    """
                    MATCH (i:Issue {id: $issue_id, tenant: $tenant})
                    OPTIONAL MATCH (i)-[:BROADER_THAN]->(broader:Issue)
                    OPTIONAL MATCH (i)<-[:BROADER_THAN]-(narrower:Issue)
                    RETURN 
                        i AS issue,
                        collect(DISTINCT broader) AS broader_issues,
                        collect(DISTINCT narrower) AS narrower_issues
                    """,
                    issue_id=issue_id,
                    tenant=tenant,
                )
                
                record = result.single()
                if record:
                    return {
                        "issue": dict(record["issue"]),
                        "broader": [dict(b) for b in record["broader_issues"] if b],
                        "narrower": [dict(n) for n in record["narrower_issues"] if n],
                    }
                return {}
                
        except Exception as e:
            logger.error(f"Error getting issue hierarchy: {e}")
            raise
    
    async def execute_query(
        self,
        cypher_query: str,
        params: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Execute a custom Cypher query.
        
        Args:
            cypher_query: The Cypher query string
            params: Query parameters
            
        Returns:
            List of result dictionaries
        """
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(cypher_query, params)
                
                results = []
                for record in result:
                    # Convert Neo4j Record to dict
                    result_dict = {}
                    for key in record.keys():
                        value = record[key]
                        # Convert Neo4j nodes to dicts
                        if hasattr(value, "__dict__"):
                            result_dict[key] = dict(value)
                        else:
                            result_dict[key] = value
                    results.append(result_dict)
                
                return results
                
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            # Return empty list if Neo4j is not available
            return []