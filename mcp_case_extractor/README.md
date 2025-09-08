# MCP Case Extractor

A comprehensive Model Context Protocol (MCP) server for extracting structured legal case information from multiple sources including conversational interfaces and document files.

## Features

### Dual-Mode Extraction System
- **Chatbox Agent**: Interactive conversational extraction through guided questions
- **File Parser**: Automatic extraction from legal documents (PDF, DOCX, TXT, HTML)

### Unified Data Model
Extracts and structures comprehensive case information:
- Basic case details (number, title, filing date, type, stage)
- Party information (plaintiffs, defendants, attorneys)
- Court information (name, jurisdiction, judge)
- Legal issues (claims, defenses, categories)
- Key facts and disputed facts
- Relief sought and damages
- Document references (cases, statutes, regulations)

### Intelligent Processing
- **Pattern-based extraction**: Regex patterns for common legal structures
- **LLM-enhanced extraction**: OpenAI GPT-4 for complex information
- **Confidence scoring**: Automated quality assessment
- **Validation system**: Multi-level validation before integration
- **Session management**: Track multiple concurrent extractions

## Installation

### Prerequisites
- Python 3.11+
- OpenAI API key (for LLM features)
- Optional: Tesseract OCR (for scanned documents)

### Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables:
```bash
export OPENAI_API_KEY="your-api-key"
export INFO_FETCHER_URL="http://localhost:8080"
export GRAPHRAG_URL="http://localhost:8081"
```

3. Update configuration (optional):
Edit `config.yaml` to customize settings.

## Usage

### Running the Server

```bash
python -m mcp_case_extractor.server config.yaml
```

### Docker Deployment

```bash
# Build the image
docker build -t mcp-case-extractor .

# Run the container
docker run -e OPENAI_API_KEY=$OPENAI_API_KEY mcp-case-extractor
```

## MCP Tools

### 1. start_chatbox_extraction
Initialize a conversational extraction session.

**Parameters:**
- `session_id` (optional): Session identifier

**Returns:**
- Session ID, greeting message, and first question

### 2. chatbox_respond
Process user responses in conversational extraction.

**Parameters:**
- `session_id`: Session identifier
- `response`: User's response text

**Returns:**
- Next question or completion status

### 3. parse_document
Extract information from a single document.

**Parameters:**
- `file_path`: Path to document file
- `session_id` (optional): Session identifier

**Returns:**
- Extracted information and confidence score

### 4. parse_batch
Process multiple documents simultaneously.

**Parameters:**
- `file_paths`: List of document paths

**Returns:**
- Results for each document

### 5. get_extraction_status
Check progress of an extraction session.

**Parameters:**
- `session_id`: Session identifier

**Returns:**
- Status, completeness score, and field summary

### 6. validate_extraction
Validate extracted information.

**Parameters:**
- `session_id`: Session identifier
- `validation_level`: minimal/basic/standard/complete

**Returns:**
- Validation results and errors

### 7. finalize_extraction
Complete extraction and send to downstream services.

**Parameters:**
- `session_id`: Session identifier
- `send_to_fetcher`: Whether to send to info fetcher

**Returns:**
- Final summary and integration results

### 8. merge_extractions
Combine multiple extraction sessions.

**Parameters:**
- `session_ids`: List of sessions to merge
- `strategy`: prefer_chatbox/prefer_document/combine

**Returns:**
- Merged session information

## Architecture

### Components

1. **Models** (`models.py`)
   - Pydantic models for structured data
   - Type-safe field definitions
   - Validation rules

2. **Chatbox Agent** (`chatbox_agent.py`)
   - Question generation engine
   - NLP-based response processing
   - Context-aware follow-ups
   - Progress tracking

3. **File Parser** (`file_parser.py`)
   - Multi-format document support
   - Text extraction pipelines
   - OCR capabilities (optional)
   - Document type detection

4. **Patterns** (`patterns.py`)
   - Regex patterns for legal structures
   - Case number formats
   - Party identification
   - Citation extraction

5. **Validators** (`validators.py`)
   - Field validation logic
   - Completeness scoring
   - Integration readiness checks

6. **Integrations** (`integrations.py`)
   - Info fetcher connection
   - GraphRAG backend integration
   - Data transformation layers
   - Retry logic

7. **Server** (`server.py`)
   - MCP protocol implementation
   - Session management
   - Tool handlers
   - Error handling

## Configuration

The `config.yaml` file controls:

- **API Keys**: OpenAI and integration services
- **Extraction Settings**: Question limits, confidence thresholds
- **File Processing**: Size limits, supported formats
- **Integration URLs**: Downstream service endpoints
- **Feature Flags**: Enable/disable specific features

## Data Flow

1. **Input Sources**
   - User conversations (chatbox)
   - Document files (parser)

2. **Processing**
   - Pattern matching
   - LLM extraction
   - Validation

3. **Output**
   - Structured ExtractedCaseInfo
   - Confidence scores
   - Validation results

4. **Integration**
   - Transform to target format
   - Send to info fetcher
   - Store in GraphRAG

## Testing

Run the test client to verify functionality:

```bash
python test_client.py
```

This demonstrates:
- Chatbox conversations
- Document parsing
- Batch processing
- Session merging
- Finalization

## Performance Considerations

- **Concurrent Sessions**: Supports up to 100 concurrent extractions
- **File Size Limit**: 10MB default (configurable)
- **Question Limit**: 15 questions per chatbox session
- **Timeout**: 30 seconds for API calls
- **Retry Logic**: Exponential backoff for failed requests

## Error Handling

The system includes comprehensive error handling:
- Input validation
- Graceful degradation (fallback to patterns if LLM fails)
- Session recovery
- Detailed error messages
- Logging at multiple levels

## Security

- Non-root Docker user
- Input sanitization
- API key management via environment variables
- File size restrictions
- Path validation

## Monitoring

Logs include:
- Extraction metrics
- Confidence scores
- Validation results
- Integration status
- Error details

## Future Enhancements

Planned improvements:
- Additional document formats
- Multi-language support
- Enhanced OCR processing
- Real-time collaboration
- Machine learning model fine-tuning
- Advanced entity recognition
- Case outcome prediction

## License

[License information]

## Support

For issues or questions, please contact the development team.