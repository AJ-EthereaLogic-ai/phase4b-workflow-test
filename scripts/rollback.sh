#!/usr/bin/env bash
# =============================================================================
# {{ cookiecutter.project_name }} - Rollback Script
# =============================================================================
# Rollback Kubernetes deployment to previous version
#
# Usage:
#   ./scripts/rollback.sh [VERSION]
#
# If VERSION is not provided, uses the last successful version from
# .last_successful_version file
#
# Environment Variables:
#   DOCKER_REGISTRY     - Docker registry URL
#   DOCKER_IMAGE_NAME   - Docker image name
#   K8S_NAMESPACE      - Kubernetes namespace
#
# Exit Codes:
#   0 - Rollback successful
#   1 - Validation failure / no version available
#   2 - Rollback failed
#   3 - Health check failed after rollback
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
DOCKER_REGISTRY="${DOCKER_REGISTRY:-{{ cookiecutter.docker_registry }}}"
DOCKER_IMAGE_NAME="${DOCKER_IMAGE_NAME:-{{ cookiecutter.project_slug }}}"
K8S_NAMESPACE="${K8S_NAMESPACE:-{{ cookiecutter.project_slug }}}"

# Version tracking
VERSION_FILE="${PROJECT_ROOT}/.last_successful_version"

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
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✓${NC} $*"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ✗${NC} $*" >&2
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠${NC} $*"
}

# =============================================================================
# Validation Functions
# =============================================================================

get_version() {
    local version="$1"

    # If version provided as argument, use it
    if [[ -n "${version}" ]]; then
        echo "${version}"
        return 0
    fi

    # Otherwise, try to read from file
    if [[ -f "${VERSION_FILE}" ]]; then
        cat "${VERSION_FILE}"
        return 0
    fi

    # No version available
    echo "none"
    return 1
}

check_prerequisites() {
    log "Checking prerequisites..."

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        return 1
    fi

    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        return 1
    fi

    # Check namespace exists
    if ! kubectl get namespace "${K8S_NAMESPACE}" &> /dev/null; then
        log_error "Namespace '${K8S_NAMESPACE}' does not exist"
        return 1
    fi

    # Check deployment exists
    if ! kubectl get deployment "${DOCKER_IMAGE_NAME}" -n "${K8S_NAMESPACE}" &> /dev/null; then
        log_error "Deployment '${DOCKER_IMAGE_NAME}' does not exist in namespace '${K8S_NAMESPACE}'"
        return 1
    fi

    log_success "Prerequisites validated"
    return 0
}

# =============================================================================
# Rollback Functions
# =============================================================================

get_current_version() {
    # Get current image tag from deployment
    kubectl get deployment "${DOCKER_IMAGE_NAME}" \
        -n "${K8S_NAMESPACE}" \
        -o jsonpath='{.spec.template.spec.containers[0].image}' \
        | awk -F: '{print $NF}'
}

rollback_using_kubectl() {
    local version="$1"

    log "Rolling back deployment to version: ${version}"

    # Update deployment with previous image
    if kubectl set image deployment/"${DOCKER_IMAGE_NAME}" \
        "${DOCKER_IMAGE_NAME}=${DOCKER_REGISTRY}/${DOCKER_IMAGE_NAME}:${version}" \
        -n "${K8S_NAMESPACE}"; then
        log_success "Deployment updated with previous image"
    else
        log_error "Failed to update deployment image"
        return 2
    fi

    # Wait for rollout
    log "Waiting for rollback to complete..."
    if kubectl rollout status deployment/"${DOCKER_IMAGE_NAME}" \
        -n "${K8S_NAMESPACE}" \
        --timeout=10m; then
        log_success "Rollback rollout completed"
    else
        log_error "Rollback rollout failed or timed out"
        return 2
    fi

    return 0
}

rollback_using_history() {
    log "Rolling back using deployment history..."

    # Use kubectl rollout undo
    if kubectl rollout undo deployment/"${DOCKER_IMAGE_NAME}" \
        -n "${K8S_NAMESPACE}"; then
        log_success "Rollback initiated"
    else
        log_error "Failed to initiate rollback"
        return 2
    fi

    # Wait for rollout
    log "Waiting for rollback to complete..."
    if kubectl rollout status deployment/"${DOCKER_IMAGE_NAME}" \
        -n "${K8S_NAMESPACE}" \
        --timeout=10m; then
        log_success "Rollback completed"
    else
        log_error "Rollback failed or timed out"
        return 2
    fi

    return 0
}

verify_rollback() {
    log "Verifying rollback health..."

    # Run health check if available
    if [[ -f "${SCRIPT_DIR}/health_check.sh" ]]; then
        if bash "${SCRIPT_DIR}/health_check.sh"; then
            log_success "Health check passed"
            return 0
        else
            log_error "Health check failed after rollback"
            return 3
        fi
    else
        log_warning "health_check.sh not found, skipping health verification"
        return 0
    fi
}

show_rollback_info() {
    local version="$1"

    echo
    echo "============================================================================="
    log_success "Rollback completed successfully!"
    echo "============================================================================="
    echo "  Rolled back to version: ${version}"
    echo "  Namespace:              ${K8S_NAMESPACE}"
    echo "  Current pods:"
    kubectl get pods -n "${K8S_NAMESPACE}" -l app="${DOCKER_IMAGE_NAME}" \
        | tail -n +2 | awk '{print "    - " $1 " (" $3 ")"}'
    echo "============================================================================="
    echo
}

# =============================================================================
# Main Function
# =============================================================================

main() {
    local version_arg="${1:-}"
    local version
    local current_version
    local exit_code=0

    echo "============================================================================="
    echo "  {{ cookiecutter.project_name }} - Deployment Rollback"
    echo "============================================================================="
    echo

    # Get version to rollback to
    if ! version=$(get_version "${version_arg}"); then
        log_error "No version specified and no previous successful version found"
        log_error "Usage: $0 [VERSION]"
        exit 1
    fi

    if [[ "${version}" == "none" ]]; then
        log_error "No version available for rollback"
        exit 1
    fi

    echo "  Target version: ${version}"
    echo "  Namespace:      ${K8S_NAMESPACE}"
    echo "  Deployment:     ${DOCKER_IMAGE_NAME}"
    echo "============================================================================="
    echo

    # Validation
    if ! check_prerequisites; then
        exit 1
    fi
    echo

    # Get current version
    current_version=$(get_current_version)
    log "Current version: ${current_version}"
    echo

    # Confirm rollback
    if [[ "${current_version}" == "${version}" ]]; then
        log_warning "Already running version ${version}"
        log "No rollback needed"
        exit 0
    fi

    log_warning "This will rollback from ${current_version} to ${version}"
    echo

    # Perform rollback
    if [[ -n "${version_arg}" ]]; then
        # Specific version provided, use kubectl set image
        if ! rollback_using_kubectl "${version}"; then
            exit_code=2
            log_error "Rollback failed"
            exit ${exit_code}
        fi
    else
        # No version provided, use kubectl rollout undo
        if ! rollback_using_history; then
            exit_code=2
            log_error "Rollback failed"
            exit ${exit_code}
        fi
    fi
    echo

    # Verify rollback
    if ! verify_rollback; then
        exit_code=3
        log_error "Rollback completed but health check failed"
        exit ${exit_code}
    fi

    # Show info
    show_rollback_info "${version}"

    return 0
}

# =============================================================================
# Script Entry Point
# =============================================================================

main "$@"

