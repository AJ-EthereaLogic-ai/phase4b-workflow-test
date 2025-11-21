#!/usr/bin/env bash
# =============================================================================
# {{ cookiecutter.project_name }} - Health Check Script
# =============================================================================
# Verify application health after deployment
#
# Usage:
#   ./scripts/health_check.sh
#
# Environment Variables:
#   K8S_NAMESPACE          - Kubernetes namespace
#   DOCKER_IMAGE_NAME      - Docker image name / deployment name
#   HEALTH_CHECK_RETRIES   - Number of retry attempts (default: 30)
#   HEALTH_CHECK_INTERVAL  - Seconds between retries (default: 10)
#
# Exit Codes:
#   0 - Health check passed
#   1 - Health check failed
#   2 - Prerequisite check failed
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
K8S_NAMESPACE="${K8S_NAMESPACE:-{{ cookiecutter.project_slug }}}"
DOCKER_IMAGE_NAME="${DOCKER_IMAGE_NAME:-{{ cookiecutter.project_slug }}}"
HEALTH_CHECK_RETRIES="${HEALTH_CHECK_RETRIES:-30}"
HEALTH_CHECK_INTERVAL="${HEALTH_CHECK_INTERVAL:-10}"
API_PORT="${API_PORT:-{{ cookiecutter.adws_api_port }}}"

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

check_prerequisites() {
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        return 2
    fi

    # Check curl
    if ! command -v curl &> /dev/null; then
        log_error "curl is not installed or not in PATH"
        return 2
    fi

    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        return 2
    fi

    return 0
}

# =============================================================================
# Health Check Functions
# =============================================================================

check_pod_status() {
    log "Checking pod status..."

    local pods
    pods=$(kubectl get pods -n "${K8S_NAMESPACE}" \
        -l app="${DOCKER_IMAGE_NAME}" \
        -o jsonpath='{.items[*].metadata.name}')

    if [[ -z "${pods}" ]]; then
        log_error "No pods found for app=${DOCKER_IMAGE_NAME}"
        return 1
    fi

    local all_ready=true
    for pod in ${pods}; do
        local status
        status=$(kubectl get pod "${pod}" -n "${K8S_NAMESPACE}" \
            -o jsonpath='{.status.phase}')

        local ready
        ready=$(kubectl get pod "${pod}" -n "${K8S_NAMESPACE}" \
            -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')

        if [[ "${status}" == "Running" && "${ready}" == "True" ]]; then
            log_success "Pod ${pod}: ${status} (Ready)"
        else
            log_warning "Pod ${pod}: ${status} (Ready: ${ready})"
            all_ready=false
        fi
    done

    if [[ "${all_ready}" == "true" ]]; then
        return 0
    else
        return 1
    fi
}

get_service_endpoint() {
    # Try to get LoadBalancer IP
    local lb_ip
    lb_ip=$(kubectl get svc "${DOCKER_IMAGE_NAME}" \
        -n "${K8S_NAMESPACE}" \
        -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")

    if [[ -n "${lb_ip}" ]]; then
        echo "${lb_ip}:${API_PORT}"
        return 0
    fi

    # Try to get LoadBalancer hostname
    local lb_hostname
    lb_hostname=$(kubectl get svc "${DOCKER_IMAGE_NAME}" \
        -n "${K8S_NAMESPACE}" \
        -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")

    if [[ -n "${lb_hostname}" ]]; then
        echo "${lb_hostname}:${API_PORT}"
        return 0
    fi

    # Fall back to port-forward
    echo "localhost:${API_PORT}"
    return 0
}

setup_port_forward() {
    local endpoint="$1"

    if [[ "${endpoint}" == "localhost:${API_PORT}" ]]; then
        log "Setting up port-forward to access service..."

        # Kill any existing port-forward on this port
        pkill -f "kubectl port-forward.*${API_PORT}:${API_PORT}" 2>/dev/null || true
        sleep 2

        # Start port-forward in background
        kubectl port-forward -n "${K8S_NAMESPACE}" \
            "svc/${DOCKER_IMAGE_NAME}" \
            "${API_PORT}:${API_PORT}" \
            >/dev/null 2>&1 &

        local pf_pid=$!
        echo "${pf_pid}"

        # Give it time to establish
        sleep 5

        return 0
    fi

    echo ""
    return 0
}

check_health_endpoint() {
    local endpoint="$1"
    local attempt="$2"

    local url="http://${endpoint}/healthz"

    if curl -sf --max-time 5 "${url}" > /dev/null 2>&1; then
        log_success "Health endpoint responded: ${url}"

        # Get response body if verbose
        local response
        response=$(curl -s --max-time 5 "${url}" 2>/dev/null || echo "{}")
        if [[ -n "${response}" && "${response}" != "{}" ]]; then
            log "Response: ${response}"
        fi

        return 0
    else
        log_warning "Health check attempt ${attempt}/${HEALTH_CHECK_RETRIES} failed"
        return 1
    fi
}

check_metrics_endpoint() {
    local endpoint="$1"

    local url="http://${endpoint}/metrics"

    log "Checking metrics endpoint..."

    if curl -sf --max-time 5 "${url}" 2>/dev/null | grep -q "adws_"; then
        log_success "Metrics endpoint accessible and returning ADWS metrics"
        return 0
    else
        log_warning "Metrics endpoint not accessible or not returning expected metrics"
        return 1
    fi
}

check_resource_usage() {
    log "Checking resource usage..."

    # Get pod metrics if metrics-server is available
    if kubectl top pods -n "${K8S_NAMESPACE}" \
        -l app="${DOCKER_IMAGE_NAME}" &>/dev/null; then

        log "Pod resource usage:"
        kubectl top pods -n "${K8S_NAMESPACE}" \
            -l app="${DOCKER_IMAGE_NAME}" \
            | tail -n +2 | while read -r line; do
                log "  ${line}"
            done
    else
        log_warning "Metrics server not available, skipping resource usage check"
    fi

    return 0
}

cleanup_port_forward() {
    local pf_pid="$1"

    if [[ -n "${pf_pid}" && "${pf_pid}" != "0" ]]; then
        log "Cleaning up port-forward..."
        kill "${pf_pid}" 2>/dev/null || true
        wait "${pf_pid}" 2>/dev/null || true
    fi
}

# =============================================================================
# Main Function
# =============================================================================

main() {
    local exit_code=0
    local pf_pid=""

    echo "============================================================================="
    echo "  {{ cookiecutter.project_name }} - Health Check"
    echo "============================================================================="
    echo "  Namespace: ${K8S_NAMESPACE}"
    echo "  App:       ${DOCKER_IMAGE_NAME}"
    echo "  Retries:   ${HEALTH_CHECK_RETRIES}"
    echo "  Interval:  ${HEALTH_CHECK_INTERVAL}s"
    echo "============================================================================="
    echo

    # Prerequisites
    if ! check_prerequisites; then
        exit 2
    fi

    # Check pod status first
    if ! check_pod_status; then
        log_error "Pod status check failed"
        exit 1
    fi
    echo

    # Get service endpoint
    log "Determining service endpoint..."
    local endpoint
    endpoint=$(get_service_endpoint)
    log "Service endpoint: ${endpoint}"
    echo

    # Setup port-forward if needed
    pf_pid=$(setup_port_forward "${endpoint}")
    if [[ -n "${pf_pid}" && "${pf_pid}" != "0" ]]; then
        trap "cleanup_port_forward ${pf_pid}" EXIT
    fi

    # Check health endpoint with retries
    log "Checking health endpoint..."
    local attempt=1
    local health_ok=false

    while [[ ${attempt} -le ${HEALTH_CHECK_RETRIES} ]]; do
        if check_health_endpoint "${endpoint}" "${attempt}"; then
            health_ok=true
            break
        fi

        if [[ ${attempt} -lt ${HEALTH_CHECK_RETRIES} ]]; then
            sleep "${HEALTH_CHECK_INTERVAL}"
        fi

        attempt=$((attempt + 1))
    done

    if [[ "${health_ok}" != "true" ]]; then
        log_error "Health endpoint check failed after ${HEALTH_CHECK_RETRIES} attempts"
        cleanup_port_forward "${pf_pid}"
        exit 1
    fi
    echo

    # Check metrics endpoint (non-fatal)
    check_metrics_endpoint "${endpoint}" || true
    echo

    # Check resource usage (non-fatal)
    check_resource_usage || true
    echo

    # Cleanup
    cleanup_port_forward "${pf_pid}"

    # Success
    echo "============================================================================="
    log_success "All health checks passed!"
    echo "============================================================================="
    echo

    return 0
}

# =============================================================================
# Script Entry Point
# =============================================================================

main "$@"

