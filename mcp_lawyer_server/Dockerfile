# MCP Lawyer Server Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY mcp_lawyer_server/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the MCP server code
COPY mcp_lawyer_server/ /app/mcp_lawyer_server/
COPY .env /app/.env

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV MCP_CONFIG_PATH=/app/mcp_lawyer_server/config.yaml

# Create a non-root user
RUN useradd -m -u 1000 mcpuser && \
    chown -R mcpuser:mcpuser /app

USER mcpuser

# Expose port for WebSocket transport (if used)
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import asyncio; from mcp_lawyer_server import MCPLawyerServer; print('healthy')" || exit 1

# Run the MCP server
CMD ["python", "-m", "mcp_lawyer_server.server"]