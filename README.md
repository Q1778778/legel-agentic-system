# Legal Analysis System - GraphRAG Enhanced

A sophisticated legal analysis system that combines Graph RAG (Retrieval-Augmented Generation) with vector search to retrieve past legal defenses and analyze legal arguments. The system uses a hybrid approach combining semantic vector search with graph traversal for enhanced legal reasoning.

# Check out the video legal-argumentation-system(https://drive.google.com/file/d/1IPjP_cayZgKfIdhvaHlx6BFdkiqTxfR6/view?usp=sharing) for the newest updates #




## 🚀 Features

- **Hybrid GraphRAG Retrieval**: Combines vector similarity search with graph-based reranking
- **Multi-Agent Analysis**: Generates defense, prosecution, and judge perspectives
- **Confidence Scoring**: Every output includes calibrated confidence metrics
- **Legal Knowledge Graph**: Rich graph structure capturing relationships between cases, lawyers, judges, and legal issues
- **Vector Search**: Fast semantic search using Qdrant with HNSW indexing
- **Multi-Tenancy**: Secure data isolation for different organizations
- **Production Ready**: Docker support, monitoring, and scalable architecture

## 📋 Architecture

The system implements the specifications from two key documents:
1. **Legal Analysis System - Enhanced DB**: Core GraphRAG retrieval and analysis
2. **Legal Data Fetcher Service**: Integration with legal APIs for data ingestion

### Technology Stack

- **Vector Database**: Qdrant for high-performance semantic search
- **Graph Database**: Neo4j for relationship-based legal knowledge
- **Framework**: FastAPI for REST APIs
- **AI/ML**: OpenAI embeddings and LLMs
- **Queue**: Celery with Redis for async tasks
- **Monitoring**: Prometheus + Grafana

## 🛠️ Installation

### Prerequisites

- Python 3.10+
- Docker and Docker Compose
- Neo4j 5.x
- Qdrant
- Redis

### Quick Start with Docker

1. Clone the repository:
```bash
git clone <repository-url>
cd legal-analysis-system
```

2. Copy environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Start all services:
```bash
docker-compose up -d
```

4. Access the services:
- API: http://localhost:8000
- API Documentation: http://localhost:8000/docs
- Neo4j Browser: http://localhost:7474
- Qdrant Dashboard: http://localhost:6333/dashboard
- Grafana: http://localhost:3001

### Local Development

1. Install Poetry:
```bash
pip install poetry
```

2. Install dependencies:
```bash
poetry install
```

3. Set up environment:
```bash
cp .env.example .env
# Configure your local settings
```

4. Start databases:
```bash
docker-compose up -d qdrant neo4j redis
```

5. Run the application:
```bash
poetry run python -m src.main
```

## 🔧 Configuration

### Environment Variables

Key configuration options in `.env`:

```env
# Supabase (optional for additional storage)
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# OpenAI
OPENAI_API_KEY=your_openai_key
EMBEDDING_MODEL=text-embedding-3-small
LLM_MODEL=gpt-4-turbo-preview

# Databases
QDRANT_HOST=localhost
QDRANT_PORT=6333
NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=your_password

# GraphRAG Parameters
GRAPHRAG_ALPHA=0.4  # Vector score weight
GRAPHRAG_BETA=0.2   # Judge match weight
GRAPHRAG_GAMMA=0.2  # Citation overlap weight
```

## 📚 API Documentation

### Core Endpoints

#### 1. Retrieve Past Defenses
```http
POST /api/v1/retrieval/past-defenses
```

Request:
```json
{
  "lawyer_id": "l_555",
  "current_issue_id": "i_42",
  "jurisdiction": "NY",
  "judge_id": "j_999",
  "limit": 10
}
```

#### 2. Analyze Arguments
```http
POST /api/v1/analysis/analyze
```

Request:
```json
{
  "bundles": [...],  // Retrieved argument bundles
  "include_prosecution": true,
  "include_judge": true,
  "max_length": 2000
}
```

#### 3. Health Check
```http
GET /api/v1/health/ready
```

## 🏗️ Project Structure

```
legal-analysis-system/
├── src/
│   ├── api/              # REST API endpoints
│   ├── core/             # Configuration and settings
│   ├── db/               # Database abstractions
│   │   ├── vector_db.py  # Qdrant interface
│   │   └── graph_db.py   # Neo4j interface
│   ├── models/           # Pydantic schemas
│   ├── services/         # Business logic
│   │   ├── graphrag_retrieval.py  # Hybrid retrieval
│   │   ├── embeddings.py          # Text vectorization
│   │   └── legal_analysis_service.py  # Multi-agent analysis
│   └── main.py           # FastAPI application
├── tests/                # Test suite
├── docker-compose.yml    # Docker orchestration
├── Dockerfile           # Container definition
└── pyproject.toml       # Python dependencies
```

## 🔍 GraphRAG Algorithm

The system implements a sophisticated GraphRAG algorithm:

1. **Issue Expansion**: Traverse graph to find related legal issues
2. **Vector Search**: Semantic search with filtered ANN
3. **Graph Reranking**: Apply graph-based boosts
4. **Diversity Constraints**: MMR for result diversity
5. **Confidence Scoring**: Calibrated probability scores

### Scoring Formula

```
final_score = α * vector_score 
            + β * judge_match 
            + γ * citation_overlap 
            + δ * outcome_boost 
            - ε * issue_hop_distance
```

## 🧪 Testing

Run the test suite:
```bash
poetry run pytest
poetry run pytest --cov=src  # With coverage
```

## 📊 Monitoring

The system includes comprehensive monitoring:

- **Prometheus Metrics**: Request counts, latencies, error rates
- **Grafana Dashboards**: Real-time visualization
- **Structured Logging**: JSON logs with correlation IDs
- **Health Checks**: Liveness and readiness probes

Access Grafana at http://localhost:3001 (default credentials: admin/admin)

## 🚦 Performance Targets

- **Retrieval P@10**: ≥ 0.7 for same-issue relevance
- **Latency P95**: < 2.0s on 1M+ segments
- **Throughput**: 1000+ cases/day ingestion
- **Availability**: 99.9% uptime

## 🔐 Security

- Multi-tenant data isolation
- API key authentication
- PII redaction before embedding
- Audit logging with trace IDs
- Secure secret management

## 📝 TODO

The following components are planned for future implementation:

- [ ] Legal Data Fetcher Service (CourtListener, CAP, RECAP integration)
- [ ] Complete ingestion pipeline with document parsing
- [ ] Advanced citation normalization
- [ ] Batch processing for large-scale ingestion
- [ ] Enhanced issue taxonomy management
- [ ] Real-time streaming updates

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

[Your License Here]

## 🙏 Acknowledgments

Built using modern AI/ML technologies and best practices for production-grade legal tech systems.
