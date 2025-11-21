#!/usr/bin/env bash
# =============================================================================
# {{ cookiecutter.project_name }} - Production Deployment Script
# =============================================================================
# Automated deployment with health checks, rollback, and validation
#
# Usage:
#   ./scripts/deploy_production.sh [VERSION]
#
# Environment Variables:
#   DEPLOYMENT_ENV          - Deployment environment (default: production)
#   DOCKER_REGISTRY         - Docker registry URL
#   DOCKER_IMAGE_NAME       - Docker image name
#   K8S_NAMESPACE          - Kubernetes namespace
#   ROLLBACK_ON_FAILURE    - Auto-rollback on failure (default: true)
#   HEALTH_CHECK_RETRIES   - Health check attempts (default: 30)
#   HEALTH_CHECK_INTERVAL  - Health check interval seconds (default: 10)
#
# Exit Codes:
#   0 - Deployment successful
#   1 - Validation/prerequisite failure
#   2 - Build failure
#   3 - Push failure
#   4 - Deployment failure
#   5 - Health check failure
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

# Deployment configuration
DEPLOYMENT_ENV="${DEPLOYMENT_ENV:-production}"
DOCKER_REGISTRY="${DOCKER_REGISTRY:-{{ cookiecutter.docker_registry }}}"
DOCKER_IMAGE_NAME="${DOCKER_IMAGE_NAME:-{{ cookiecutter.project_slug }}}"
K8S_NAMESPACE="${K8S_NAMESPACE:-{{ cookiecutter.project_slug }}}"
ROLLBACK_ON_FAILURE="${ROLLBACK_ON_FAILURE:-true}"
HEALTH_CHECK_RETRIES="${HEALTH_CHECK_RETRIES:-30}"
HEALTH_CHECK_INTERVAL="${HEALTH_CHECK_INTERVAL:-10}"

# Version tracking
VERSION_FILE="${PROJECT_ROOT}/.last_successful_version"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

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

validate_environment() {
    log "Validating environment configuration..."

    local required_vars=(
        "DEPLOYMENT_ENV"
        "DOCKER_REGISTRY"
        "DOCKER_IMAGE_NAME"
        "K8S_NAMESPACE"
    )

    local missing_vars=()
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing_vars+=("$var")
        fi
    done

    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log_error "Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            echo "  - $var"
        done
        return 1
    fi

    log_success "Environment variables validated"
    return 0
}

check_prerequisites() {
    log "Checking prerequisites..."

    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        return 1
    fi
    log_success "Docker: $(docker --version)"

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        return 1
    fi
    log_success "kubectl: $(kubectl version --client --short 2>/dev/null || kubectl version --client)"

    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        log_error "Configure kubectl with: kubectl config use-context <context-name>"
        return 1
    fi
    log_success "Kubernetes cluster connected"

    # Check namespace exists
    if ! kubectl get namespace "${K8S_NAMESPACE}" &> /dev/null; then
        log_warning "Namespace '${K8S_NAMESPACE}' does not exist, will be created"
    else
        log_success "Namespace '${K8S_NAMESPACE}' exists"
    fi

    return 0
}

# =============================================================================
# Docker Functions
# =============================================================================

build_docker_image() {
    local version="$1"
    local image_tag="${DOCKER_REGISTRY}/${DOCKER_IMAGE_NAME}:${version}"
    local latest_tag="${DOCKER_REGISTRY}/${DOCKER_IMAGE_NAME}:latest"

    log "Building Docker image: ${image_tag}"

    if ! docker build \
        --tag "${image_tag}" \
        --tag "${latest_tag}" \
        --label "version=${version}" \
        --label "build.timestamp=${TIMESTAMP}" \
        --label "deployment.env=${DEPLOYMENT_ENV}" \
        "${PROJECT_ROOT}"; then
        log_error "Docker build failed"
        return 2
    fi

    log_success "Docker image built successfully"

    # Show image size
    local image_size
    image_size=$(docker images "${image_tag}" --format "{{.Size}}")
    log "Image size: ${image_size}"

    return 0
}

push_docker_image() {
    local version="$1"
    local image_tag="${DOCKER_REGISTRY}/${DOCKER_IMAGE_NAME}:${version}"
    local latest_tag="${DOCKER_REGISTRY}/${DOCKER_IMAGE_NAME}:latest"

    log "Pushing Docker image to registry..."

    local max_retries=3
    local retry=0

    while [[ $retry -lt $max_retries ]]; do
        if docker push "${image_tag}" && docker push "${latest_tag}"; then
            log_success "Docker image pushed successfully"
            return 0
        fi

        retry=$((retry + 1))
        if [[ $retry -lt $max_retries ]]; then
            log_warning "Push failed, retrying (${retry}/${max_retries})..."
            sleep 5
        fi
    done

    log_error "Failed to push Docker image after ${max_retries} attempts"
    return 3
}

# =============================================================================
# Kubernetes Functions
# =============================================================================

deploy_kubernetes() {
    local version="$1"

    log "Deploying to Kubernetes namespace: ${K8S_NAMESPACE}"

    # Update kustomization with new image tag
    cd "${PROJECT_ROOT}/k8s" || return 4

    if [[ -f kustomization.yaml ]]; then
        log "Updating kustomization with image: ${DOCKER_REGISTRY}/${DOCKER_IMAGE_NAME}:${version}"
        kubectl kustomize edit set image \
            "${DOCKER_REGISTRY}/${DOCKER_IMAGE_NAME}=${DOCKER_REGISTRY}/${DOCKER_IMAGE_NAME}:${version}"
    fi

    # Apply namespace first (if doesn't exist)
    if ! kubectl get namespace "${K8S_NAMESPACE}" &> /dev/null; then
        log "Creating namespace: ${K8S_NAMESPACE}"
        kubectl apply -f namespace.yaml
    fi

    # Apply all manifests using kustomize
    log "Applying Kubernetes manifests..."
    if ! kubectl apply -k .; then
        log_error "Kubernetes deployment failed"
        return 4
    fi

    log_success "Kubernetes manifests applied"

    # Wait for rollout
    if ! wait_for_rollout; then
        log_error "Deployment rollout failed"
        return 4
    fi

    return 0
}

wait_for_rollout() {
    log "Waiting for deployment rollout..."

    if kubectl rollout status deployment/"${DOCKER_IMAGE_NAME}" \
        --namespace="${K8S_NAMESPACE}" \
        --timeout=10m; then
        log_success "Deployment rollout completed"
        return 0
    else
        log_error "Deployment rollout failed or timed out"
        return 1
    fi
}

verify_health() {
    log "Verifying application health..."

    # Run health check script
    if [[ -f "${SCRIPT_DIR}/health_check.sh" ]]; then
        if bash "${SCRIPT_DIR}/health_check.sh"; then
            log_success "Health check passed"
            return 0
        else
            log_error "Health check failed"
            return 5
        fi
    else
        log_warning "health_check.sh not found, skipping health verification"
        return 0
    fi
}

# =============================================================================
# Rollback Functions
# =============================================================================

get_previous_version() {
    if [[ -f "${VERSION_FILE}" ]]; then
        cat "${VERSION_FILE}"
    else
        echo "none"
    fi
}

rollback_deployment() {
    local previous_version="$1"

    log_error "Deployment failed!"

    if [[ "${ROLLBACK_ON_FAILURE}" != "true" ]]; then
        log_warning "Automatic rollback is disabled (ROLLBACK_ON_FAILURE=false)"
        return 1
    fi

    if [[ "${previous_version}" == "none" ]]; then
        log_error "No previous version found, cannot rollback"
        return 1
    fi

    log "Rolling back to previous version: ${previous_version}"

    if [[ -f "${SCRIPT_DIR}/rollback.sh" ]]; then
        if bash "${SCRIPT_DIR}/rollback.sh" "${previous_version}"; then
            log_success "Rollback completed successfully"
            return 0
        else
            log_error "Rollback failed"
            return 1
        fi
    else
        log_error "rollback.sh not found, cannot perform rollback"
        return 1
    fi
}

save_successful_version() {
    local version="$1"
    echo "${version}" > "${VERSION_FILE}"
    log "Saved successful version: ${version}"
}

# =============================================================================
# Cleanup Functions
# =============================================================================

cleanup() {
    log "Performing cleanup..."
    # Add any cleanup tasks here (temporary files, etc.)
}

# =============================================================================
# Main Function
# =============================================================================

main() {
    local version="${1:-latest}"
    local exit_code=0

    echo "============================================================================="
    echo "  {{ cookiecutter.project_name }} - Production Deployment"
    echo "============================================================================="
    echo "  Environment: ${DEPLOYMENT_ENV}"
    echo "  Version:     ${version}"
    echo "  Registry:    ${DOCKER_REGISTRY}"
    echo "  Image:       ${DOCKER_IMAGE_NAME}"
    echo "  Namespace:   ${K8S_NAMESPACE}"
    echo "  Timestamp:   ${TIMESTAMP}"
    echo "============================================================================="
    echo

    # Get previous version for potential rollback
    local previous_version
    previous_version=$(get_previous_version)
    log "Previous successful version: ${previous_version}"
    echo

    # Validation
    if ! validate_environment; then
        exit 1
    fi
    echo

    if ! check_prerequisites; then
        exit 1
    fi
    echo

    # Build
    if ! build_docker_image "${version}"; then
        exit 2
    fi
    echo

    # Push
    if ! push_docker_image "${version}"; then
        exit 3
    fi
    echo

    # Deploy
    if ! deploy_kubernetes "${version}"; then
        exit_code=4
        rollback_deployment "${previous_version}" || true
        cleanup
        exit ${exit_code}
    fi
    echo

    # Verify
    if ! verify_health; then
        exit_code=5
        rollback_deployment "${previous_version}" || true
        cleanup
        exit ${exit_code}
    fi
    echo

    # Success!
    save_successful_version "${version}"
    cleanup

    echo
    echo "============================================================================="
    log_success "Deployment completed successfully!"
    echo "============================================================================="
    echo "  Version deployed: ${version}"
    echo "  Namespace:        ${K8S_NAMESPACE}"
    echo "  Pods:"
    kubectl get pods -n "${K8S_NAMESPACE}" -l app="${DOCKER_IMAGE_NAME}" | tail -n +2 | awk '{print "    - " $1 " (" $3 ")"}'
    echo "============================================================================="
    echo

    return 0
}

# =============================================================================
# Script Entry Point
# =============================================================================

# Trap errors and cleanup
trap cleanup EXIT

# Run main function
main "$@"

