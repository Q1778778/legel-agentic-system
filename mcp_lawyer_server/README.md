# MCP Lawyer Server - Conversational Legal AI Assistant

A comprehensive Model Context Protocol (MCP) server implementation for a conversational lawyer agent system with advanced opponent simulation capabilities.

## Features

### Core Capabilities

1. **Conversational Legal Consultation**
   - AI-powered legal advice based on precedents and case law
   - Context-aware responses maintaining conversation history
   - Integration with GraphRAG retrieval system for precedent search

2. **Opponent Simulation**
   - Simulates opposing counsel's responses to arguments
   - Searches for cases with opposite outcomes
   - Identifies weaknesses in arguments
   - Provides counter-argument suggestions

3. **Deep Case Analysis**
   - Comprehensive case strength assessment
   - Risk identification and mitigation strategies
   - Timeline projections and strategic options
   - Success probability calculations

4. **Session Management**
   - Multi-session support with context preservation
   - Conversation history tracking
   - Session export/import capabilities
   - Automatic cleanup of expired sessions

## Architecture

```
mcp_lawyer_server/
├── server.py              # Main MCP server implementation
├── lawyer_agent.py        # AI lawyer agent logic
├── opponent_simulator.py  # Opposing counsel simulation
├── conversation_manager.py # Session management
├── legal_context.py       # Legal context data structures
├── config.yaml           # Configuration file
├── requirements.txt      # Python dependencies
├── Dockerfile           # Container configuration
└── run_server.py        # Standalone runner
```

## MCP Tools

The server exposes the following MCP tools:

### 1. `initialize_session`
Initialize a new legal consultation session with case and lawyer information.

**Parameters:**
- `case_info`: Case details (caption, court, jurisdiction, etc.)
- `lawyer_info`: Our lawyer's information
- `opposing_counsel_info`: Opposing counsel's information
- `session_id`: Optional custom session ID

### 2. `consult_lawyer`
Main conversational interface for legal consultation.

**Parameters:**
- `query`: Legal question or argument
- `session_id`: Active session ID
- `include_precedents`: Whether to search for precedents (default: true)
- `simulate_opposition`: Whether to simulate opposing response (default: false)

### 3. `simulate_opponent`
Simulate opposing counsel's response to an argument.

**Parameters:**
- `our_argument`: The argument to counter
- `session_id`: Active session ID

### 4. `analyze_case`
Perform deep analysis of the case.

**Parameters:**
- `session_id`: Active session ID
- `deep_analysis`: Enable comprehensive analysis (default: true)

### 5. `get_relevant_precedents`
Search for relevant legal precedents.

**Parameters:**
- `search_query`: Legal issue or query
- `session_id`: Optional session for context
- `limit`: Maximum results (1-20, default: 5)

### 6. `get_session_summary`
Get summary of current session.

**Parameters:**
- `session_id`: Session to summarize

### 7. `end_session`
End a consultation session.

**Parameters:**
- `session_id`: Session to end
- `export_data`: Export session data before ending (default: false)

## Installation

### Prerequisites
- Python 3.11+
- Docker and Docker Compose (optional)
- OpenAI API key

### Local Installation

1. Install dependencies:
```bash
cd mcp_lawyer_server
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export OPENAI_API_KEY="your-api-key"
export MCP_CONFIG_PATH="config.yaml"
```

3. Configure the server:
Edit `config.yaml` to set your preferences.

### Docker Installation

1. Build the container:
```bash
docker-compose build mcp-lawyer-server
```

2. Run with Docker Compose:
```bash
docker-compose up mcp-lawyer-server
```

## Usage

### Standalone Mode

Run the server directly:
```bash
python mcp_lawyer_server/run_server.py
```

### With MCP Client

The server uses stdio transport by default. Connect using any MCP-compatible client:

```python
import mcp
from mcp.client import Client
from mcp.client.stdio import stdio_client

# Create client
async with stdio_client(
    ["python", "-m", "mcp_lawyer_server.server"]
) as (read, write):
    async with Client(read, write) as client:
        # Initialize session
        result = await client.call_tool(
            "initialize_session",
            {
                "case_info": {
                    "caption": "Smith v. Johnson",
                    "court": "District Court",
                    "jurisdiction": "CA",
                    "case_type": "Contract Dispute"
                }
            }
        )
        session_id = result["session_id"]
        
        # Consult lawyer
        response = await client.call_tool(
            "consult_lawyer",
            {
                "session_id": session_id,
                "query": "What are our options for breach of contract claim?",
                "simulate_opposition": True
            }
        )
```

## Configuration

Key configuration options in `config.yaml`:

```yaml
# GraphRAG Backend
graphrag:
  base_url: "http://localhost:8000"
  
# OpenAI Settings  
openai:
  model: "gpt-4-turbo-preview"
  temperature: 0.7
  
# Opponent Simulation
opponent_simulation:
  search_strategy:
    opposite_outcome_weight: 0.8
    counter_argument_weight: 0.7
  max_precedents: 5
  
# Session Management
session:
  max_sessions: 1000
  session_ttl: 3600  # 1 hour
```

## Integration with GraphRAG

The server integrates with the existing GraphRAG retrieval system:

1. **Retrieval Endpoint**: `/api/v1/retrieval/past-defenses`
2. **Custom Filters**: For opponent simulation, uses `outcome_opposite` filter
3. **Hybrid Scoring**: Combines vector similarity with graph-based features

## Opponent Simulation Strategy

The opponent simulator employs a multi-step approach:

1. **Search Phase**
   - Queries for cases with opposite outcomes
   - Filters for winning arguments from opposing side
   - Identifies successful counter-arguments

2. **Analysis Phase**
   - Identifies weaknesses in our arguments
   - Analyzes precedent-based vulnerabilities
   - Assesses logical gaps

3. **Generation Phase**
   - Creates opposing counsel's response
   - Incorporates relevant precedents
   - Exploits identified weaknesses

4. **Assessment Phase**
   - Evaluates response strength
   - Provides counter-argument suggestions
   - Offers strategic recommendations

## Development

### Running Tests

```bash
pytest tests/test_mcp_server.py -v
```

### Adding New Tools

1. Define tool in `server.py` `_register_tools()` method
2. Implement handler method
3. Update tool documentation

### Extending Opponent Simulation

Modify `OpponentSimulator` class in `opponent_simulator.py`:
- Adjust search strategies in `_search_opposing_precedents()`
- Enhance weakness identification in `_identify_argument_weaknesses()`
- Customize response generation in `_generate_opposing_response()`

## Performance Considerations

- **Session Caching**: Precedent searches are cached for 10 minutes
- **Async Operations**: All I/O operations are asynchronous
- **Connection Pooling**: HTTP connections are pooled for GraphRAG API
- **Memory Management**: Sessions auto-expire after TTL

## Error Handling

The server includes comprehensive error handling:
- Graceful fallback to mock data when GraphRAG is unavailable
- Retry logic for API calls with exponential backoff
- Session recovery from exported data
- Detailed error logging with structlog

## Security

- API key authentication support
- Session isolation between clients
- Input validation on all tool parameters
- Secure handling of sensitive case information

## Monitoring

The server provides:
- Structured JSON logging
- Session statistics endpoint
- Performance metrics per operation
- Health check endpoint for Docker

## License

This project is part of the Legal Agentic System.

## Support

For issues or questions:
1. Check the logs in `mcp_lawyer_server.log`
2. Verify GraphRAG backend is running
3. Ensure OpenAI API key is configured
4. Review session state with `get_session_summary` tool