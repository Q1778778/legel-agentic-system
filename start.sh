#!/bin/bash

# Legal Analysis System - One-Click Startup Script
# =================================================

set -e  # Exit immediately on error

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if command exists
check_command() {
    if ! command -v $1 &> /dev/null; then
        print_error "$1 is not installed. Please install $1 first"
        exit 1
    fi
}

# Cleanup function
cleanup() {
    print_info "Stopping services..."
    
    # Stop all Streamlit instances
    if [ ! -z "$STREAMLIT_PID" ]; then
        kill $STREAMLIT_PID 2>/dev/null || true
    fi
    if [ ! -z "$STREAMLIT_8502_PID" ]; then
        kill $STREAMLIT_8502_PID 2>/dev/null || true
    fi
    if [ ! -z "$STREAMLIT_8503_PID" ]; then
        kill $STREAMLIT_8503_PID 2>/dev/null || true
    fi
    if [ ! -z "$STREAMLIT_8504_PID" ]; then
        kill $STREAMLIT_8504_PID 2>/dev/null || true
    fi
    
    # Stop FastAPI
    if [ ! -z "$FASTAPI_PID" ]; then
        kill $FASTAPI_PID 2>/dev/null || true
    fi
    
    # Stop NLWeb
    if [ ! -z "$NLWEB_PID" ]; then
        kill $NLWEB_PID 2>/dev/null || true
    fi
    
    # Stop Docker containers if they exist
    if command -v docker-compose &> /dev/null; then
        docker-compose -f docker-compose.fast.yml down 2>/dev/null || true
    fi
    
    print_success "All services stopped"
}

# Set cleanup hook
trap cleanup EXIT INT TERM

# Main function
main() {
    echo "======================================"
    echo "   Legal Analysis System Startup"
    echo "======================================"
    echo

    # Check required commands
    print_info "Checking system environment..."
    check_command docker
    check_command docker-compose
    check_command python3
    # Check streamlit as a Python module instead of command
    if ! python3 -m streamlit --version &> /dev/null; then
        print_error "streamlit is not installed. Please install streamlit first (pip install streamlit)"
        exit 1
    fi
    print_success "Environment check passed"
    echo

    # Check .env file
    if [ ! -f .env ]; then
        print_warning ".env file does not exist"
        if [ -f .env.example ]; then
            print_info "Creating .env file from .env.example..."
            cp .env.example .env
            print_warning "Please edit .env file to configure required environment variables (e.g., OPENAI_API_KEY)"
            echo "Please run this script again after configuration"
            exit 1
        else
            print_error ".env.example file not found, cannot continue"
            exit 1
        fi
    fi

    # Stop any existing containers
    print_info "Cleaning up old containers..."
    docker-compose -f docker-compose.fast.yml down 2>/dev/null || true
    print_success "Cleanup completed"
    echo

    # Start Docker services
    print_info "Starting backend services (Docker)..."
    docker-compose -f docker-compose.fast.yml up -d --build
    
    # Wait for services to start
    print_info "Waiting for services to start..."
    MAX_RETRIES=30
    RETRY_COUNT=0
    
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if curl -s http://localhost:8000/api/v1/health/ > /dev/null 2>&1; then
            print_success "Backend services started successfully"
            break
        fi
        echo -n "."
        sleep 2
        RETRY_COUNT=$((RETRY_COUNT + 1))
    done
    echo
    
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        print_error "Backend services failed to start. Please check logs:"
        echo "docker logs court-argument-simulator"
        exit 1
    fi

    # Display service status
    print_info "Checking service status..."
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "court-sim|court-argument" || true
    echo

    # Start NLWeb service (modify config to use port 8080)
    if [ -d "NLWeb" ]; then
        print_info "Starting NLWeb service..."
        
        # Source .env file to export environment variables
        if [ -f ".env" ]; then
            print_info "Loading environment variables from .env..."
            export $(grep -v '^#' .env | xargs)
        fi
        
        # First, modify the config file to use port 8080
        if [ -f "NLWeb/config/config_webserver.yaml" ]; then
            # Backup original config
            cp NLWeb/config/config_webserver.yaml NLWeb/config/config_webserver.yaml.bak 2>/dev/null
            # Change port from 8000 to 8080
            sed -i '' 's/port: 8000/port: 8080/g' NLWeb/config/config_webserver.yaml 2>/dev/null || \
            sed -i 's/port: 8000/port: 8080/g' NLWeb/config/config_webserver.yaml
            print_info "Changed NLWeb port to 8080"
        fi
        
        # Navigate to NLWeb python directory
        cd NLWeb/code/python
        
        # Source environment variables if available
        if [ -f "../set_keys.sh" ]; then
            print_info "Loading NLWeb environment variables..."
            source ../set_keys.sh
        elif [ -f "../../set_keys.sh" ]; then
            source ../../set_keys.sh
        fi
        
        # Set environment variable for config path
        export CONFIG_PATH="../../config"
        
        # Start NLWeb server normally
        python3 -m webserver.aiohttp_server > /tmp/nlweb.log 2>&1 &
        NLWEB_PID=$!
        cd ../../..
        
        # Wait for NLWeb to start
        sleep 4
        
        # Check if NLWeb started successfully
        if ps -p $NLWEB_PID > /dev/null; then
            # NLWeb now runs on port 8080
            if curl -s http://localhost:8080/health > /dev/null 2>&1; then
                print_success "NLWeb service started successfully on port 8080"
            else
                print_warning "NLWeb process started but health check failed"
            fi
        else
            print_warning "NLWeb service failed to start (check /tmp/nlweb.log for details)"
            NLWEB_PID=""
        fi
    else
        print_warning "NLWeb directory not found, skipping NLWeb service"
    fi
    echo
    
    # Check MCP Servers availability
    print_info "Checking MCP servers..."
    
    # Run MCP demo script to show status
    if [ -f "mcp_demo.py" ]; then
        python3 mcp_demo.py | while IFS= read -r line; do
            if [[ $line == *"✅"* ]]; then
                print_success "${line#*✅ }"
            elif [[ $line == *"Status: Available"* ]]; then
                echo "    $line"
            fi
        done
    else
        # Fallback if demo script doesn't exist
        if [ -d "mcp_lawyer_server" ]; then
            print_success "MCP Lawyer Server configured (stdio mode)"
        fi
        if [ -d "mcp_case_extractor" ]; then
            print_success "MCP Case Extractor configured (stdio mode)"
        fi
    fi
    
    print_info "MCP servers use stdio protocol and connect on-demand"
    echo

    # Start FastAPI backend (without Docker)
    print_info "Starting FastAPI backend service..."
    if ! curl -s http://localhost:8000/api/v1/health/ > /dev/null 2>&1; then
        python3 -m src.main > /tmp/fastapi.log 2>&1 &
        FASTAPI_PID=$!
        
        # Wait for FastAPI to start
        sleep 3
        
        if curl -s http://localhost:8000/api/v1/health/ > /dev/null 2>&1; then
            print_success "FastAPI backend started successfully"
        else
            print_warning "FastAPI backend failed to start (check /tmp/fastapi.log)"
        fi
    else
        print_success "FastAPI backend already running"
    fi
    echo
    
    # Start all Streamlit frontends
    print_info "Starting frontend services..."
    
    # Start enhanced version (8502)
    if ! curl -s http://localhost:8502 > /dev/null 2>&1; then
        python3 -m streamlit run web_app_enhanced.py --server.port 8502 --server.headless true > /tmp/streamlit_8502.log 2>&1 &
        STREAMLIT_8502_PID=$!
        sleep 2
        print_success "Enhanced Case Management UI started (port 8502)"
    else
        print_success "Enhanced UI already running (port 8502)"
    fi
    
    # Start MCP integrated version (8503)
    if ! curl -s http://localhost:8503 > /dev/null 2>&1; then
        python3 -m streamlit run web_app_mcp_integrated.py --server.port 8503 --server.headless true > /tmp/streamlit_8503.log 2>&1 &
        STREAMLIT_8503_PID=$!
        sleep 2
        print_success "MCP Integrated UI started (port 8503)"
    else
        print_success "MCP Integrated UI already running (port 8503)"
    fi
    
    # Start Apple style version (8504)
    if ! curl -s http://localhost:8504 > /dev/null 2>&1; then
        python3 -m streamlit run web_app_apple.py --server.port 8504 --server.headless true > /tmp/streamlit_8504.log 2>&1 &
        STREAMLIT_8504_PID=$!
        sleep 2
        print_success "Apple Style UI started (port 8504)"
    else
        print_success "Apple Style UI already running (port 8504)"
    fi
    
    # Start original version (8501) - optional
    if ! curl -s http://localhost:8501 > /dev/null 2>&1; then
        python3 -m streamlit run web_app.py --server.port 8501 --server.headless true > /tmp/streamlit_8501.log 2>&1 &
        STREAMLIT_PID=$!
        sleep 2
        print_success "Original UI started (port 8501)"
    else
        print_success "Original UI already running (port 8501)"
    fi
    
    print_success "All frontend services started successfully"
    echo

    # Display access information
    echo "======================================"
    print_success "System startup complete!"
    echo "======================================"
    echo
    echo "🌐 Access URLs:"
    echo "  - Enhanced Case Management: http://localhost:8502 (推荐)"
    echo "  - MCP Integrated UI: http://localhost:8503"
    echo "  - Apple Style UI: http://localhost:8504"
    echo "  - Original UI: http://localhost:8501"
    echo "  - API Documentation: http://localhost:8000/docs"
    if [ ! -z "$NLWEB_PID" ]; then
        echo "  - NLWeb Interface: http://localhost:8080"
    fi
    echo "  - Neo4j Browser: http://localhost:7474"
    echo "  - Qdrant Dashboard: http://localhost:6333/dashboard"
    echo
    echo "📝 View logs:"
    echo "  - FastAPI: tail -f /tmp/fastapi.log"
    echo "  - Streamlit 8502: tail -f /tmp/streamlit_8502.log"
    echo "  - Streamlit 8503: tail -f /tmp/streamlit_8503.log"
    echo "  - Streamlit 8504: tail -f /tmp/streamlit_8504.log"
    echo "  - Backend containers: docker-compose -f docker-compose.fast.yml logs -f"
    if [ ! -z "$NLWEB_PID" ]; then
        echo "  - NLWeb: tail -f /tmp/nlweb.log"
    fi
    echo
    echo "🛑 Stop services:"
    echo "  - Press Ctrl+C to stop all services"
    echo "  - Or run: ./stop.sh"
    echo
    print_info "All services are running, press Ctrl+C to stop..."
    
    # Wait for user interrupt - keep the script running
    while true; do
        sleep 1
    done
}

# Run main function
main