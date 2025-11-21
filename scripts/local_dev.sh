#!/usr/bin/env bash
# =============================================================================
# {{ cookiecutter.project_name }} - Local Development Helper
# =============================================================================
# Unified local development script with subcommands
#
# Usage:
#   ./scripts/local_dev.sh <command> [options]
#
# Commands:
#   start       Start all services with docker compose
#   stop        Stop all services
#   restart     Restart services
#   logs        Tail logs (use -f <service> to filter)
#   shell       Open shell in ADWS container
#   test        Run tests in container
#   build       Build Docker image locally
#   clean       Clean volumes and containers
#   status      Show service status
#   help        Show this help message
#
# Examples:
#   ./scripts/local_dev.sh start
#   ./scripts/local_dev.sh logs -f {{ cookiecutter.project_slug }}
#   ./scripts/local_dev.sh shell
#   ./scripts/local_dev.sh test
#   ./scripts/local_dev.sh clean
# =============================================================================

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load environment variables
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
fi

# Configuration
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
PROJECT_NAME="{{ cookiecutter.project_slug }}"
SERVICE_NAME="{{ cookiecutter.project_slug }}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# Logging Functions
# =============================================================================

log() {
    echo -e "${BLUE}[local-dev]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[local-dev] ✓${NC} $*"
}

log_error() {
    echo -e "${RED}[local-dev] ✗${NC} $*" >&2
}

log_warning() {
    echo -e "${YELLOW}[local-dev] ⚠${NC} $*"
}

# =============================================================================
# Utility Functions
# =============================================================================

check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi

    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose v2 plugin is not installed"
        log_error "Install with: https://docs.docker.com/compose/install/"
        exit 1
    fi
}

check_compose_file() {
    if [[ ! -f "${COMPOSE_FILE}" ]]; then
        log_error "docker-compose.yml not found at: ${COMPOSE_FILE}"
        exit 1
    fi
}

# =============================================================================
# Command Functions
# =============================================================================

cmd_start() {
    log "Starting all services..."

    docker compose -f "${COMPOSE_FILE}" up -d

    log_success "Services started"
    log "Waiting for services to be healthy..."
    sleep 3

    cmd_status
}

cmd_stop() {
    log "Stopping all services..."

    docker compose -f "${COMPOSE_FILE}" down

    log_success "Services stopped"
}

cmd_restart() {
    log "Restarting services..."

    docker compose -f "${COMPOSE_FILE}" restart

    log_success "Services restarted"
    cmd_status
}

cmd_logs() {
    local service="${2:-}"

    if [[ "$1" == "-f" && -n "${service}" ]]; then
        log "Tailing logs for service: ${service}"
        docker compose -f "${COMPOSE_FILE}" logs -f "${service}"
    else
        log "Tailing logs for all services"
        docker compose -f "${COMPOSE_FILE}" logs -f
    fi
}

cmd_shell() {
    log "Opening shell in ${SERVICE_NAME} container..."

    # Check if container is running
    if ! docker compose -f "${COMPOSE_FILE}" ps "${SERVICE_NAME}" | grep -q "Up"; then
        log_error "Container '${SERVICE_NAME}' is not running"
        log "Start services first with: $0 start"
        exit 1
    fi

    docker compose -f "${COMPOSE_FILE}" exec "${SERVICE_NAME}" /bin/bash
}

cmd_test() {
    log "Running tests in container..."

    # Check if container is running
    if ! docker compose -f "${COMPOSE_FILE}" ps "${SERVICE_NAME}" | grep -q "Up"; then
        log_warning "Container '${SERVICE_NAME}' is not running, starting it..."
        cmd_start
        sleep 3
    fi

    docker compose -f "${COMPOSE_FILE}" exec "${SERVICE_NAME}" pytest

    log_success "Tests completed"
}

cmd_build() {
    log "Building Docker image..."

    docker compose -f "${COMPOSE_FILE}" build

    log_success "Docker image built"

    # Show image size
    local image_size
    image_size=$(docker images "${PROJECT_NAME}" --format "{{.Size}}" | head -1)
    log "Image size: ${image_size}"
}

cmd_clean() {
    log_warning "This will remove all containers, volumes, and orphan containers"
    read -p "Are you sure? (yes/no): " -r confirm

    if [[ "${confirm}" != "yes" ]]; then
        log "Cancelled"
        exit 0
    fi

    log "Cleaning up..."

    # Stop and remove everything
    docker compose -f "${COMPOSE_FILE}" down -v --remove-orphans

    # Remove dangling images
    log "Removing dangling images..."
    docker image prune -f

    log_success "Cleanup completed"
}

cmd_status() {
    log "Service status:"
    echo

    docker compose -f "${COMPOSE_FILE}" ps

    echo
    log "Docker stats (press Ctrl+C to exit):"
    docker stats --no-stream \
        $(docker compose -f "${COMPOSE_FILE}" ps -q 2>/dev/null) \
        2>/dev/null || log_warning "No running containers"
}

cmd_help() {
    cat <<EOF
{{ cookiecutter.project_name }} - Local Development Helper

Usage:
    $0 <command> [options]

Commands:
    start       Start all services with docker compose
    stop        Stop all services
    restart     Restart services
    logs        Tail logs
                  $0 logs           # All services
                  $0 logs -f <svc>  # Specific service
    shell       Open bash shell in ADWS container
    test        Run pytest in container
    build       Build Docker image locally
    clean       Remove all containers, volumes, and orphan containers
    status      Show service status and resource usage
    help        Show this help message

Examples:
    $0 start
    $0 logs -f ${SERVICE_NAME}
    $0 shell
    $0 test
    $0 build
    $0 clean
    $0 status

Environment:
    Configuration is loaded from .env file if present

Services:
    - ${SERVICE_NAME}  - ADWS API server
{%- if cookiecutter.enable_monitoring == "yes" %}
    - prometheus          - Metrics collection
    - grafana             - Metrics visualization
{%- endif %}

For more information, see:
    - README.md
    - DEPLOYMENT.md
    - docker-compose.yml
EOF
}

# =============================================================================
# Main Function
# =============================================================================

main() {
    # Check prerequisites
    check_docker
    check_compose_file

    # Parse command
    local command="${1:-help}"

    case "${command}" in
        start)
            cmd_start
            ;;
        stop)
            cmd_stop
            ;;
        restart)
            cmd_restart
            ;;
        logs)
            shift
            cmd_logs "$@"
            ;;
        shell)
            cmd_shell
            ;;
        test)
            cmd_test
            ;;
        build)
            cmd_build
            ;;
        clean)
            cmd_clean
            ;;
        status)
            cmd_status
            ;;
        help|--help|-h)
            cmd_help
            ;;
        *)
            log_error "Unknown command: ${command}"
            echo
            cmd_help
            exit 1
            ;;
    esac
}

# =============================================================================
# Script Entry Point
# =============================================================================

main "$@"

