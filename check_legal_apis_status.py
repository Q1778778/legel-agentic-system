#!/usr/bin/env python3
"""
Legal APIs Status Checker

This script checks the availability and status of all legal data APIs,
monitors API quotas, tests connectivity, and provides a comprehensive
health report of the legal data integration system.

Features:
- API endpoint availability testing
- Rate limit and quota monitoring
- Response time measurement
- Error rate tracking
- Database connectivity check
- System health dashboard
- Automated health reports

Usage:
    python check_legal_apis_status.py [--verbose] [--json] [--save-report]
"""

import asyncio
import sys
import os
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import aiohttp
from dataclasses import dataclass, asdict
from enum import Enum

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class APIStatus(Enum):
    """API status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"


class DatabaseStatus(Enum):
    """Database status enumeration."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    NOT_CONFIGURED = "not_configured"


@dataclass
class APIHealthResult:
    """API health check result."""
    name: str
    status: APIStatus
    response_time_ms: float
    status_code: Optional[int]
    error_message: Optional[str]
    rate_limit_remaining: Optional[int]
    rate_limit_reset: Optional[datetime]
    endpoint_tested: str
    timestamp: datetime


@dataclass
class DatabaseHealthResult:
    """Database health check result."""
    name: str
    status: DatabaseStatus
    connection_time_ms: float
    error_message: Optional[str]
    version: Optional[str]
    node_count: Optional[int]
    timestamp: datetime


@dataclass
class SystemHealthReport:
    """Complete system health report."""
    timestamp: datetime
    overall_status: str
    api_results: List[APIHealthResult]
    database_results: List[DatabaseHealthResult]
    summary: Dict[str, Any]
    recommendations: List[str]


class LegalAPIHealthChecker:
    """Legal API health checker."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize health checker."""
        self.config = self._load_config(config_path)
        self.session: Optional[aiohttp.ClientSession] = None
        
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Load API configuration."""
        default_config = {
            "apis": {
                "courtlistener": {
                    "base_url": "https://www.courtlistener.com/api/rest/v4",
                    "health_endpoint": "/search/",
                    "timeout": 10,
                    "requires_auth": True
                },
                "cap": {
                    "base_url": "https://api.case.law/v1",
                    "health_endpoint": "/cases/",
                    "timeout": 10,
                    "requires_auth": False
                },
                "govinfo": {
                    "base_url": "https://api.govinfo.gov",
                    "health_endpoint": "/collections",
                    "timeout": 10,
                    "requires_auth": True
                },
                "openstates": {
                    "base_url": "https://openstates.org/api/v3",
                    "health_endpoint": "/people",
                    "timeout": 10,
                    "requires_auth": True
                },
                "ecfr": {
                    "base_url": "https://www.ecfr.gov/api/versioner/v1",
                    "health_endpoint": "/titles",
                    "timeout": 10,
                    "requires_auth": False
                },
                "oyez": {
                    "base_url": "https://api.oyez.org",
                    "health_endpoint": "/cases",
                    "timeout": 10,
                    "requires_auth": False
                }
            },
            "databases": {
                "neo4j": {
                    "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                    "user": os.getenv("NEO4J_USER", "neo4j"),
                    "password": os.getenv("NEO4J_PASSWORD", "password")
                },
                "pinecone": {
                    "api_key": os.getenv("PINECONE_API_KEY"),
                    "environment": os.getenv("PINECONE_ENVIRONMENT")
                },
                "weaviate": {
                    "url": os.getenv("WEAVIATE_URL", "http://localhost:8080"),
                    "api_key": os.getenv("WEAVIATE_API_KEY")
                }
            }
        }
        
        if config_path and Path(config_path).exists():
            import yaml
            with open(config_path) as f:
                file_config = yaml.safe_load(f)
                default_config.update(file_config)
        
        return default_config
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def check_api_health(self, api_name: str, api_config: Dict[str, Any]) -> APIHealthResult:
        """Check health of a specific API."""
        start_time = time.time()
        
        try:
            base_url = api_config["base_url"]
            endpoint = api_config["health_endpoint"]
            timeout = api_config.get("timeout", 10)
            requires_auth = api_config.get("requires_auth", False)
            
            url = f"{base_url}{endpoint}"
            headers = {}
            
            # Add authentication if required
            if requires_auth:
                api_key = os.getenv(f"{api_name.upper()}_API_KEY")
                if api_key:
                    if api_name == "courtlistener":
                        headers["Authorization"] = f"Token {api_key}"
                    elif api_name == "govinfo":
                        headers["X-API-Key"] = api_key
                    elif api_name == "openstates":
                        headers["X-API-Key"] = api_key
                else:
                    return APIHealthResult(
                        name=api_name,
                        status=APIStatus.AUTH_ERROR,
                        response_time_ms=0,
                        status_code=None,
                        error_message="API key not configured",
                        rate_limit_remaining=None,
                        rate_limit_reset=None,
                        endpoint_tested=url,
                        timestamp=datetime.now()
                    )
            
            # Make the request
            async with self.session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                response_time = (time.time() - start_time) * 1000
                
                # Parse rate limit headers
                rate_limit_remaining = None
                rate_limit_reset = None
                
                if "x-ratelimit-remaining" in response.headers:
                    rate_limit_remaining = int(response.headers["x-ratelimit-remaining"])
                if "x-ratelimit-reset" in response.headers:
                    reset_timestamp = int(response.headers["x-ratelimit-reset"])
                    rate_limit_reset = datetime.fromtimestamp(reset_timestamp)
                
                # Determine status
                if response.status == 200:
                    status = APIStatus.HEALTHY
                elif response.status == 429:
                    status = APIStatus.RATE_LIMITED
                elif 400 <= response.status < 500:
                    status = APIStatus.AUTH_ERROR if response.status in [401, 403] else APIStatus.DEGRADED
                else:
                    status = APIStatus.DOWN
                
                return APIHealthResult(
                    name=api_name,
                    status=status,
                    response_time_ms=response_time,
                    status_code=response.status,
                    error_message=None if status == APIStatus.HEALTHY else f"HTTP {response.status}",
                    rate_limit_remaining=rate_limit_remaining,
                    rate_limit_reset=rate_limit_reset,
                    endpoint_tested=url,
                    timestamp=datetime.now()
                )
        
        except asyncio.TimeoutError:
            return APIHealthResult(
                name=api_name,
                status=APIStatus.DOWN,
                response_time_ms=(time.time() - start_time) * 1000,
                status_code=None,
                error_message="Request timeout",
                rate_limit_remaining=None,
                rate_limit_reset=None,
                endpoint_tested=url,
                timestamp=datetime.now()
            )
        
        except Exception as e:
            return APIHealthResult(
                name=api_name,
                status=APIStatus.DOWN,
                response_time_ms=(time.time() - start_time) * 1000,
                status_code=None,
                error_message=str(e),
                rate_limit_remaining=None,
                rate_limit_reset=None,
                endpoint_tested=url,
                timestamp=datetime.now()
            )
    
    async def check_neo4j_health(self) -> DatabaseHealthResult:
        """Check Neo4j database health."""
        start_time = time.time()
        
        try:
            from neo4j import GraphDatabase
            
            config = self.config["databases"]["neo4j"]
            uri = config["uri"]
            user = config["user"]
            password = config["password"]
            
            driver = GraphDatabase.driver(uri, auth=(user, password))
            
            with driver.session() as session:
                result = session.run("CALL dbms.components() YIELD name, versions")
                components = list(result)
                
                # Get node count
                node_result = session.run("MATCH (n) RETURN count(n) as count")
                node_count = node_result.single()["count"]
                
                # Get Neo4j version
                version = components[0]["versions"][0] if components else "Unknown"
            
            driver.close()
            connection_time = (time.time() - start_time) * 1000
            
            return DatabaseHealthResult(
                name="neo4j",
                status=DatabaseStatus.CONNECTED,
                connection_time_ms=connection_time,
                error_message=None,
                version=version,
                node_count=node_count,
                timestamp=datetime.now()
            )
        
        except ImportError:
            return DatabaseHealthResult(
                name="neo4j",
                status=DatabaseStatus.NOT_CONFIGURED,
                connection_time_ms=0,
                error_message="Neo4j driver not installed",
                version=None,
                node_count=None,
                timestamp=datetime.now()
            )
        
        except Exception as e:
            return DatabaseHealthResult(
                name="neo4j",
                status=DatabaseStatus.ERROR,
                connection_time_ms=(time.time() - start_time) * 1000,
                error_message=str(e),
                version=None,
                node_count=None,
                timestamp=datetime.now()
            )
    
    async def check_pinecone_health(self) -> DatabaseHealthResult:
        """Check Pinecone database health."""
        start_time = time.time()
        
        try:
            import pinecone
            
            config = self.config["databases"]["pinecone"]
            api_key = config["api_key"]
            environment = config["environment"]
            
            if not api_key or not environment:
                return DatabaseHealthResult(
                    name="pinecone",
                    status=DatabaseStatus.NOT_CONFIGURED,
                    connection_time_ms=0,
                    error_message="API key or environment not configured",
                    version=None,
                    node_count=None,
                    timestamp=datetime.now()
                )
            
            pinecone.init(api_key=api_key, environment=environment)
            indexes = pinecone.list_indexes()
            
            connection_time = (time.time() - start_time) * 1000
            
            return DatabaseHealthResult(
                name="pinecone",
                status=DatabaseStatus.CONNECTED,
                connection_time_ms=connection_time,
                error_message=None,
                version="Cloud",
                node_count=len(indexes),
                timestamp=datetime.now()
            )
        
        except ImportError:
            return DatabaseHealthResult(
                name="pinecone",
                status=DatabaseStatus.NOT_CONFIGURED,
                connection_time_ms=0,
                error_message="Pinecone client not installed",
                version=None,
                node_count=None,
                timestamp=datetime.now()
            )
        
        except Exception as e:
            return DatabaseHealthResult(
                name="pinecone",
                status=DatabaseStatus.ERROR,
                connection_time_ms=(time.time() - start_time) * 1000,
                error_message=str(e),
                version=None,
                node_count=None,
                timestamp=datetime.now()
            )
    
    async def check_weaviate_health(self) -> DatabaseHealthResult:
        """Check Weaviate database health."""
        start_time = time.time()
        
        try:
            config = self.config["databases"]["weaviate"]
            url = config["url"]
            api_key = config.get("api_key")
            
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            async with self.session.get(f"{url}/v1/meta", headers=headers) as response:
                if response.status == 200:
                    meta = await response.json()
                    version = meta.get("version", "Unknown")
                    
                    connection_time = (time.time() - start_time) * 1000
                    
                    return DatabaseHealthResult(
                        name="weaviate",
                        status=DatabaseStatus.CONNECTED,
                        connection_time_ms=connection_time,
                        error_message=None,
                        version=version,
                        node_count=None,  # Would need additional query
                        timestamp=datetime.now()
                    )
                else:
                    return DatabaseHealthResult(
                        name="weaviate",
                        status=DatabaseStatus.ERROR,
                        connection_time_ms=(time.time() - start_time) * 1000,
                        error_message=f"HTTP {response.status}",
                        version=None,
                        node_count=None,
                        timestamp=datetime.now()
                    )
        
        except Exception as e:
            return DatabaseHealthResult(
                name="weaviate",
                status=DatabaseStatus.ERROR,
                connection_time_ms=(time.time() - start_time) * 1000,
                error_message=str(e),
                version=None,
                node_count=None,
                timestamp=datetime.now()
            )
    
    async def run_comprehensive_health_check(self) -> SystemHealthReport:
        """Run comprehensive health check of all systems."""
        print("🔍 Running comprehensive health check...")
        
        # Check all APIs
        print("\n📡 Checking API endpoints...")
        api_tasks = [
            self.check_api_health(name, config)
            for name, config in self.config["apis"].items()
        ]
        api_results = await asyncio.gather(*api_tasks, return_exceptions=True)
        
        # Filter out exceptions and convert to proper results
        valid_api_results = []
        for result in api_results:
            if isinstance(result, APIHealthResult):
                valid_api_results.append(result)
            elif isinstance(result, Exception):
                logger.error(f"API health check failed: {result}")
        
        # Check databases
        print("\n🗄️  Checking database connections...")
        db_results = []
        
        # Neo4j
        neo4j_result = await self.check_neo4j_health()
        db_results.append(neo4j_result)
        
        # Pinecone
        pinecone_result = await self.check_pinecone_health()
        db_results.append(pinecone_result)
        
        # Weaviate
        weaviate_result = await self.check_weaviate_health()
        db_results.append(weaviate_result)
        
        # Generate summary
        healthy_apis = sum(1 for r in valid_api_results if r.status == APIStatus.HEALTHY)
        total_apis = len(valid_api_results)
        
        connected_dbs = sum(1 for r in db_results if r.status == DatabaseStatus.CONNECTED)
        total_dbs = len(db_results)
        
        # Determine overall status
        if healthy_apis == total_apis and connected_dbs > 0:
            overall_status = "excellent"
        elif healthy_apis >= total_apis // 2:
            overall_status = "good"
        elif healthy_apis > 0:
            overall_status = "degraded"
        else:
            overall_status = "critical"
        
        # Generate recommendations
        recommendations = []
        
        auth_errors = [r for r in valid_api_results if r.status == APIStatus.AUTH_ERROR]
        if auth_errors:
            recommendations.append(
                f"Configure API keys for: {', '.join(r.name for r in auth_errors)}"
            )
        
        down_apis = [r for r in valid_api_results if r.status == APIStatus.DOWN]
        if down_apis:
            recommendations.append(
                f"Check connectivity for: {', '.join(r.name for r in down_apis)}"
            )
        
        disconnected_dbs = [r for r in db_results if r.status == DatabaseStatus.ERROR]
        if disconnected_dbs:
            recommendations.append(
                f"Fix database connections: {', '.join(r.name for r in disconnected_dbs)}"
            )
        
        if not recommendations:
            recommendations.append("System is operating optimally")
        
        summary = {
            "total_apis": total_apis,
            "healthy_apis": healthy_apis,
            "api_success_rate": healthy_apis / total_apis if total_apis > 0 else 0,
            "total_databases": total_dbs,
            "connected_databases": connected_dbs,
            "database_connection_rate": connected_dbs / total_dbs if total_dbs > 0 else 0,
            "avg_api_response_time": sum(r.response_time_ms for r in valid_api_results) / len(valid_api_results) if valid_api_results else 0
        }
        
        return SystemHealthReport(
            timestamp=datetime.now(),
            overall_status=overall_status,
            api_results=valid_api_results,
            database_results=db_results,
            summary=summary,
            recommendations=recommendations
        )


def print_health_report(report: SystemHealthReport, verbose: bool = False):
    """Print health report to console."""
    print(f"\n{'='*80}")
    print(f"🏥 Legal Data APIs Health Report")
    print(f"{'='*80}")
    print(f"Generated: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Overall Status: {get_status_emoji(report.overall_status)} {report.overall_status.upper()}")
    
    # Summary section
    print(f"\n📊 Summary:")
    print(f"   APIs: {report.summary['healthy_apis']}/{report.summary['total_apis']} healthy ({report.summary['api_success_rate']:.1%})")
    print(f"   Databases: {report.summary['connected_databases']}/{report.summary['total_databases']} connected ({report.summary['database_connection_rate']:.1%})")
    print(f"   Avg API Response Time: {report.summary['avg_api_response_time']:.0f}ms")
    
    # API Results
    print(f"\n📡 API Endpoints:")
    for result in report.api_results:
        status_emoji = get_status_emoji(result.status.value)
        print(f"   {status_emoji} {result.name.upper():<15} - {result.status.value.title()}")
        if verbose:
            print(f"      Response Time: {result.response_time_ms:.0f}ms")
            print(f"      Endpoint: {result.endpoint_tested}")
            if result.error_message:
                print(f"      Error: {result.error_message}")
            if result.rate_limit_remaining is not None:
                print(f"      Rate Limit: {result.rate_limit_remaining} remaining")
    
    # Database Results
    print(f"\n🗄️  Databases:")
    for result in report.database_results:
        status_emoji = get_status_emoji(result.status.value)
        print(f"   {status_emoji} {result.name.upper():<15} - {result.status.value.title()}")
        if verbose:
            if result.connection_time_ms > 0:
                print(f"      Connection Time: {result.connection_time_ms:.0f}ms")
            if result.version:
                print(f"      Version: {result.version}")
            if result.node_count is not None:
                print(f"      Nodes/Indexes: {result.node_count}")
            if result.error_message:
                print(f"      Error: {result.error_message}")
    
    # Recommendations
    print(f"\n💡 Recommendations:")
    for rec in report.recommendations:
        print(f"   • {rec}")
    
    print(f"\n{'='*80}")


def get_status_emoji(status: str) -> str:
    """Get emoji for status."""
    emoji_map = {
        "healthy": "✅",
        "excellent": "✅",
        "good": "✅",
        "connected": "✅",
        "degraded": "⚠️",
        "rate_limited": "⚠️",
        "down": "❌",
        "error": "❌",
        "critical": "❌",
        "auth_error": "🔑",
        "not_configured": "⚙️",
        "unknown": "❓"
    }
    return emoji_map.get(status, "❓")


async def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Legal APIs Health Checker")
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--save-report', help='Save report to file')
    parser.add_argument('--config', help='Configuration file path')
    
    args = parser.parse_args()
    
    try:
        async with LegalAPIHealthChecker(args.config) as checker:
            report = await checker.run_comprehensive_health_check()
            
            if args.json:
                # Convert to JSON-serializable format
                report_dict = asdict(report)
                # Convert datetime objects to strings
                report_dict['timestamp'] = report.timestamp.isoformat()
                for api_result in report_dict['api_results']:
                    api_result['timestamp'] = api_result['timestamp'].isoformat() if api_result['timestamp'] else None
                    if api_result['rate_limit_reset']:
                        api_result['rate_limit_reset'] = api_result['rate_limit_reset'].isoformat()
                for db_result in report_dict['database_results']:
                    db_result['timestamp'] = db_result['timestamp'].isoformat() if db_result['timestamp'] else None
                
                print(json.dumps(report_dict, indent=2))
            else:
                print_health_report(report, args.verbose)
            
            # Save report if requested
            if args.save_report:
                save_path = Path(args.save_report)
                save_path.parent.mkdir(parents=True, exist_ok=True)
                
                report_dict = asdict(report)
                # Convert datetime objects to strings for JSON serialization
                def convert_datetime(obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    return obj
                
                import json
                with open(save_path, 'w') as f:
                    json.dump(report_dict, f, indent=2, default=convert_datetime)
                
                print(f"\n💾 Report saved to: {save_path}")
            
            # Return appropriate exit code
            if report.overall_status in ["excellent", "good"]:
                return 0
            elif report.overall_status == "degraded":
                return 1
            else:
                return 2
    
    except KeyboardInterrupt:
        print("\n⏹️  Health check interrupted by user")
        return 130
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        logger.error("Health check failed", error=str(e), exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)