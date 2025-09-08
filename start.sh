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
    print_info "Stopping backend services..."
    docker compose -f docker-compose.fast.yml stop  # Changed from 'down' to 'stop' to keep containers
    print_success "Backend services stopped (containers preserved for debugging)"
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

    # Stop any existing containers (but keep them for debugging)
    print_info "Stopping any running containers..."
    docker compose -f docker-compose.fast.yml stop 2>/dev/null || true
    print_success "Containers stopped (preserved for debugging)"
    echo

    # Start Docker services
    print_info "Starting backend services (Docker)..."
    docker compose -f docker-compose.fast.yml up -d --build
    
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
        echo ""
        echo "Container is preserved for debugging. To check logs:"
        echo "  docker logs court-argument-simulator"
        echo "  docker ps -a  # to see all containers"
        echo ""
        echo "To remove containers manually:"
        echo "  docker compose -f docker-compose.fast.yml down"
        exit 1
    fi

    # Display service status
    print_info "Checking service status..."
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "court-sim|court-argument" || true
    echo


    # Display access information
    echo "======================================"
    print_success "Backend API startup complete!"
    echo "======================================"
    echo
    echo "API Access:"
    echo "  - Backend API: http://localhost:8000"
    echo "  - API Documentation: http://localhost:8000/docs"
    echo "  - React Frontend: http://localhost:3000 (run separately)"
    echo
    echo "Database Access:"
    echo "  - Neo4j Browser: http://localhost:7474"
    echo "  - Qdrant Dashboard: http://localhost:6333/dashboard"
    echo
    echo "View logs:"
    echo "  - Backend logs: docker logs -f court-argument-simulator"
    echo "  - All containers: docker compose -f docker-compose.fast.yml logs -f"
    echo
    echo "Stop services:"
    echo "  - Press Ctrl+C to stop backend services"
    echo
    print_info "Backend API is running, press Ctrl+C to stop..."
    
    # Keep script running until interrupted
    while true; do
        sleep 1
    done
}

# Run main function
main