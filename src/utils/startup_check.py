"""Startup validation and health check for the legal agent system."""

import asyncio
import os
import sys
from typing import Dict, Any, List
import structlog
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.config_validator import ConfigValidator
from db.vector_db import VectorDB
from db.graph_db import GraphDB
from services.graphrag_retrieval import GraphRAGRetrieval
from agents.orchestrator import DebateOrchestrator, DebateMode

logger = structlog.get_logger()
console = Console()


class StartupChecker:
    """Performs startup checks for the legal agent system."""
    
    def __init__(self):
        """Initialize the startup checker."""
        self.checks_passed = []
        self.checks_failed = []
        self.warnings = []
    
    async def check_openai_api(self) -> Dict[str, Any]:
        """Check OpenAI API configuration and connection."""
        try:
            api_key = ConfigValidator.get_openai_api_key()
            if not api_key:
                return {
                    "status": "warning",
                    "message": "No OpenAI API key found - agents will run in mock mode",
                    "details": "Set OPENAI_API_KEY environment variable to enable AI agents"
                }
            
            # Test connection
            is_valid = await ConfigValidator.validate_openai_connection(api_key)
            if is_valid:
                return {
                    "status": "success",
                    "message": "OpenAI API connection successful",
                    "details": f"API key configured and validated"
                }
            else:
                return {
                    "status": "error",
                    "message": "OpenAI API connection failed",
                    "details": "Check API key validity and network connection"
                }
        except Exception as e:
            return {
                "status": "error",
                "message": "OpenAI API check failed",
                "details": str(e)
            }
    
    async def check_vector_db(self) -> Dict[str, Any]:
        """Check Qdrant vector database connection."""
        try:
            vdb = VectorDB()
            # Try to get collection info
            collections = await vdb.client.get_collections()
            return {
                "status": "success",
                "message": "Qdrant vector DB connected",
                "details": f"{len(collections.collections)} collections found"
            }
        except Exception as e:
            return {
                "status": "warning",
                "message": "Qdrant vector DB not available",
                "details": f"Will use mock data: {str(e)}"
            }
    
    async def check_graph_db(self) -> Dict[str, Any]:
        """Check Neo4j graph database connection."""
        try:
            gdb = GraphDB()
            # Try a simple query
            result = await gdb.execute_query("MATCH (n) RETURN count(n) as count LIMIT 1")
            node_count = result[0]["count"] if result else 0
            return {
                "status": "success",
                "message": "Neo4j graph DB connected",
                "details": f"{node_count} nodes in graph"
            }
        except Exception as e:
            return {
                "status": "warning",
                "message": "Neo4j graph DB not available",
                "details": f"Will use mock data: {str(e)}"
            }
    
    async def check_graphrag_service(self) -> Dict[str, Any]:
        """Check GraphRAG retrieval service."""
        try:
            from models.schemas import RetrievalRequest
            
            service = GraphRAGRetrieval()
            # Test with a simple query
            request = RetrievalRequest(
                issue_text="Test legal issue",
                limit=1
            )
            response = await service.retrieve_past_defenses(request)
            return {
                "status": "success",
                "message": "GraphRAG service operational",
                "details": f"Retrieved {len(response.bundles)} bundles"
            }
        except Exception as e:
            return {
                "status": "warning",
                "message": "GraphRAG service degraded",
                "details": f"Will use fallback: {str(e)}"
            }
    
    async def check_agents(self) -> Dict[str, Any]:
        """Check agent initialization."""
        try:
            # Try to initialize an orchestrator
            orchestrator = DebateOrchestrator(
                mode=DebateMode.SINGLE,
                max_turns=1,
                enable_feedback=False
            )
            
            # Check if agents were initialized
            agent_count = len(orchestrator.agents)
            
            # Check if using mock mode
            config = ConfigValidator.get_agent_config("base")
            if config["enable_mock"]:
                return {
                    "status": "warning",
                    "message": f"Agents initialized in mock mode ({agent_count} agents)",
                    "details": "Set OPENAI_API_KEY to enable real AI agents"
                }
            else:
                return {
                    "status": "success",
                    "message": f"Agents initialized with AI ({agent_count} agents)",
                    "details": "OpenAI API connected successfully"
                }
        except Exception as e:
            return {
                "status": "error",
                "message": "Agent initialization failed",
                "details": str(e)
            }
    
    async def run_all_checks(self) -> Dict[str, Any]:
        """Run all startup checks."""
        console.print("\n[bold cyan]Running Startup Checks...[/bold cyan]\n")
        
        checks = [
            ("OpenAI API", self.check_openai_api()),
            ("Vector Database", self.check_vector_db()),
            ("Graph Database", self.check_graph_db()),
            ("GraphRAG Service", self.check_graphrag_service()),
            ("Agent System", self.check_agents()),
        ]
        
        results = []
        for name, check_coro in checks:
            console.print(f"Checking {name}...", end=" ")
            result = await check_coro
            result["name"] = name
            results.append(result)
            
            if result["status"] == "success":
                console.print("[green]✓[/green]")
                self.checks_passed.append(name)
            elif result["status"] == "warning":
                console.print("[yellow]⚠[/yellow]")
                self.warnings.append(name)
            else:
                console.print("[red]✗[/red]")
                self.checks_failed.append(name)
        
        return {
            "results": results,
            "passed": self.checks_passed,
            "failed": self.checks_failed,
            "warnings": self.warnings,
            "summary": self._generate_summary()
        }
    
    def _generate_summary(self) -> str:
        """Generate a summary of the checks."""
        total = len(self.checks_passed) + len(self.checks_failed) + len(self.warnings)
        
        if len(self.checks_failed) > 0:
            return f"System has critical issues: {len(self.checks_failed)}/{total} checks failed"
        elif len(self.warnings) > 0:
            return f"System operational with limitations: {len(self.warnings)}/{total} checks have warnings"
        else:
            return f"System fully operational: {total}/{total} checks passed"
    
    def display_results(self, results: Dict[str, Any]):
        """Display check results in a formatted table."""
        console.print("\n")
        
        # Create results table
        table = Table(title="Startup Check Results", show_lines=True)
        table.add_column("Component", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center")
        table.add_column("Details", style="dim")
        
        for result in results["results"]:
            status_icon = {
                "success": "[green]✓ Success[/green]",
                "warning": "[yellow]⚠ Warning[/yellow]",
                "error": "[red]✗ Error[/red]"
            }.get(result["status"], result["status"])
            
            table.add_row(
                result["name"],
                status_icon,
                result["details"]
            )
        
        console.print(table)
        
        # Display summary panel
        summary_color = "green" if len(results["failed"]) == 0 else "red" if len(results["failed"]) > 0 else "yellow"
        panel = Panel(
            results["summary"],
            title="System Status",
            border_style=summary_color,
            expand=False
        )
        console.print("\n", panel, "\n")
        
        # Display recommendations if needed
        if results["warnings"] or results["failed"]:
            console.print("[bold]Recommendations:[/bold]")
            
            if "OpenAI API" in results["warnings"] + results["failed"]:
                console.print("  • Set OPENAI_API_KEY environment variable for AI-powered agents")
            
            if "Vector Database" in results["warnings"]:
                console.print("  • Start Qdrant: docker run -p 6333:6333 qdrant/qdrant")
            
            if "Graph Database" in results["warnings"]:
                console.print("  • Start Neo4j: docker run -p 7687:7687 neo4j")
            
            console.print("")


async def main():
    """Main entry point for startup checks."""
    checker = StartupChecker()
    results = await checker.run_all_checks()
    checker.display_results(results)
    
    # Return exit code based on results
    if len(results["failed"]) > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())