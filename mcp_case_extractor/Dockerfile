# Multi-stage build for MCP Case Extractor Server
FROM python:3.11-slim as builder

# Install system dependencies for document processing
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    libpoppler-cpp-dev \
    tesseract-ocr \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpoppler-cpp-dev \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 extractor

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/extractor/.local

# Copy application code
COPY --chown=extractor:extractor . .

# Switch to non-root user
USER extractor

# Add local bin to PATH
ENV PATH=/home/extractor/.local/bin:$PATH

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV MCP_MODE=stdio

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run the server
ENTRYPOINT ["python", "-m", "mcp_case_extractor.server"]
CMD ["config.yaml"]