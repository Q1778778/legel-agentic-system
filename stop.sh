#!/bin/bash

# Legal Analysis System - Stop Script
# ====================================

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

# Main function
main() {
    echo "======================================"
    echo "   Stopping Legal Analysis System"
    echo "======================================"
    echo

    # Stop Docker services
    print_info "Stopping Docker services..."
    if docker-compose -f docker-compose.fast.yml down 2>/dev/null; then
        print_success "Docker services stopped"
    else
        print_warning "Docker services were not running or failed to stop"
    fi

    # Stop Streamlit
    print_info "Stopping Streamlit frontend..."
    if pkill -f "streamlit run web_app.py" 2>/dev/null; then
        print_success "Streamlit stopped"
    else
        print_warning "Streamlit was not running"
    fi

    # Stop NLWeb
    print_info "Stopping NLWeb service..."
    if pkill -f "webserver.aiohttp_server" 2>/dev/null; then
        print_success "NLWeb stopped"
    elif pkill -f "startup_aiohttp.sh" 2>/dev/null; then
        print_success "NLWeb stopped"
    else
        print_warning "NLWeb was not running"
    fi

    # Stop MCP servers
    print_info "Stopping MCP servers..."
    MCP_STOPPED=false
    
    # Stop MCP Lawyer Server
    if pkill -f "mcp_lawyer_server.server" 2>/dev/null; then
        print_success "MCP Lawyer Server stopped"
        MCP_STOPPED=true
    elif pkill -f "mcp_lawyer_server" 2>/dev/null; then
        print_success "MCP Lawyer Server stopped"
        MCP_STOPPED=true
    fi
    
    # Stop MCP Case Extractor
    if pkill -f "mcp_case_extractor/server.py" 2>/dev/null; then
        print_success "MCP Case Extractor stopped"
        MCP_STOPPED=true
    elif pkill -f "mcp_case_extractor" 2>/dev/null; then
        print_success "MCP Case Extractor stopped"
        MCP_STOPPED=true
    fi
    
    # Stop MCP Opponent Simulator (if exists)
    if pkill -f "mcp_opponent_simulator" 2>/dev/null; then
        print_success "MCP Opponent Simulator stopped"
        MCP_STOPPED=true
    fi
    
    if [ "$MCP_STOPPED" = false ]; then
        print_warning "No MCP servers were running"
    fi

    echo
    echo "======================================"
    print_success "All services stopped!"
    echo "======================================"
    echo
    echo "To restart services, run: ./start.sh"
}

# Run main function
main