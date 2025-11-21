# Phase4B Test Project - Deployment Guide

Comprehensive deployment guide for Phase4B Test Project.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Docker Deployment](#docker-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

## Overview

This project includes production-ready deployment configurations for:

- **Local Development**: Docker Compose for development and testing
- **Docker**: Production Docker images with multi-stage builds
- **Kubernetes**: Complete K8s manifests with autoscaling and monitoring
- **Monitoring**: Prometheus metrics and Grafana dashboards

## Prerequisites

### Required

- **Docker** 24.0+ with Compose v2 plugin
- **kubectl** 1.27+ (for Kubernetes deployment)
- **Python** 3.11+

### Optional

- **Kubernetes Cluster**: minikube, kind, k3s, or cloud provider (GKE, EKS, AKS)
- **Metrics Server**: For horizontal pod autoscaling
- **Ingress Controller**: NGINX or Traefik for external access

## Local Development

### Quick Start

Use the local development helper script:

```bash
# Start all services
./scripts/local_dev.sh start

# View logs
./scripts/local_dev.sh logs

# Run tests
./scripts/local_dev.sh test

# Open shell
./scripts/local_dev.sh shell

# Stop services
./scripts/local_dev.sh stop
```

### Manual Docker Compose

```bash
# Start services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

### Access Services

- **API**: http://localhost:8000
- **Health**: http://localhost:8000/healthz
- **Metrics**: http://localhost:8000/metrics
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

## Docker Deployment

### Build Docker Image

```bash
docker build -t localhost:5000/phase4b_test:latest .
```

### Push to Registry

```bash
docker push localhost:5000/phase4b_test:latest
```

### Run Container

```bash
docker run -d \
  --name phase4b_test \
  -p 8000:8000 \
  -e ANTHROPIC_API_KEY=your-key \
  localhost:5000/phase4b_test:latest
```

## Kubernetes Deployment

### Prerequisites

1. Configure kubectl to access your cluster:
   ```bash
   kubectl config use-context your-context
   ```

2. Create secrets:
   ```bash
   cp k8s/secret.yaml.example k8s/secret.yaml
   # Edit k8s/secret.yaml with base64-encoded API keys
   kubectl apply -f k8s/secret.yaml
   ```

### Deploy Using Scripts

**Automated Deployment** (Recommended):

```bash
# Deploy with auto-rollback on failure
./scripts/deploy_production.sh v1.0.0

# The script will:
# - Build and push Docker image
# - Deploy to Kubernetes
# - Wait for rollout to complete
# - Verify health checks
# - Rollback automatically if deployment fails
```

**Manual Deployment**:

```bash
# Using Kustomize
kubectl apply -k k8s/

# Or apply manifests individually
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml  # optional
kubectl apply -f k8s/hpa.yaml      # optional
```

### Verify Deployment

```bash
# Check deployment status
kubectl get all -n phase4b_test

# Check pod logs
kubectl logs -f deployment/phase4b_test -n phase4b_test

# Run health check
./scripts/health_check.sh
```

### Rollback Deployment

```bash
# Automatic rollback to last successful version
./scripts/rollback.sh

# Rollback to specific version
./scripts/rollback.sh v0.9.0
```

## CI/CD with GitHub Actions

### Available Workflows

The project includes 4 GitHub Actions workflows for automated CI/CD:

#### 1. CI - Test and Lint (`.github/workflows/ci.yml`)

Runs on every push and pull request:

```yaml
# Automatically runs:
- Code formatting check (ruff format)
- Linting (ruff check)
- Type checking (mypy)
- Unit tests with coverage (pytest)
- Security scanning (bandit, safety)
```

**Required Secrets**: None (uses mock API keys for tests)

#### 2. Build and Push Docker Image (`.github/workflows/docker-build.yml`)

Triggered by version tags or manual dispatch:

```bash
# Create a tag to trigger build
git tag v1.0.0
git push origin v1.0.0

# Or trigger manually from GitHub Actions UI
```

**Features**:
- Multi-architecture builds (amd64, arm64)
- Automatic versioning from git tags
- Trivy security scanning
- SBOM generation

**Required Secrets**:
- `DOCKER_REGISTRY_USER`: Docker registry username
- `DOCKER_REGISTRY_PASSWORD`: Docker registry password/token

#### 3. Deploy to Kubernetes (`.github/workflows/deploy.yml`)

Manual deployment workflow with auto-rollback:

```bash
# Trigger from GitHub Actions UI with:
- Environment: staging or production
- Version: v1.0.0
- Enable rollback: true
```

**Features**:
- Automated deployment using `deploy_production.sh`
- Health verification using `health_check.sh`
- Auto-rollback on failure (configurable)

**Required Secrets**:
- `KUBECONFIG`: Base64-encoded kubeconfig file
- `DOCKER_REGISTRY_USER`: Docker registry credentials
- `DOCKER_REGISTRY_PASSWORD`: Docker registry credentials

#### 4. Release Pipeline (`.github/workflows/release.yml`)

Full release orchestration (test → build → deploy):

```bash
# Triggered automatically when a release is published, or manually
```

**Pipeline Steps**:
1. Validate version format (vX.Y.Z)
2. Run CI tests
3. Build and push Docker image
4. Deploy to staging
5. Run staging smoke tests
6. Deploy to production (with manual approval)
7. Create release notes

**Environment Protection**: Production deployment requires manual approval

### Setting Up GitHub Actions

1. **Add Repository Secrets**:

   Go to Settings → Secrets and variables → Actions:

   ```
   DOCKER_REGISTRY_USER=your-username
   DOCKER_REGISTRY_PASSWORD=your-token
   KUBECONFIG=base64-encoded-kubeconfig
   ```

2. **Encode Kubeconfig** (for deployment workflows):

   ```bash
   cat ~/.kube/config | base64 -w 0
   ```

3. **Configure Environments** (optional):

   Create `staging` and `production` environments with protection rules:
   - Settings → Environments → New environment
   - Add required reviewers for production
   - Configure environment secrets

### Using the Workflows

**Typical Release Flow**:

```bash
# 1. Create a release branch
git checkout -b release/v1.0.0

# 2. Update version, test locally
./scripts/local_dev.sh test

# 3. Push and create PR
git push origin release/v1.0.0

# 4. CI runs automatically on PR

# 5. Merge to main

# 6. Create and push tag
git tag v1.0.0
git push origin v1.0.0

# 7. Docker build triggers automatically

# 8. Create GitHub Release (or use release.yml workflow)

# 9. Release pipeline deploys to staging → production
```

**Quick Deploy** (without full release):

```bash
# Use deploy workflow manually from GitHub Actions UI
# Or use the deployment script locally:
./scripts/deploy_production.sh v1.0.0
```

## Monitoring

### Prometheus

Access Prometheus at http://localhost:9090

**Useful Queries**:

```promql
# Total workflows
sum(adws_workflows_total)

# Active workflows
adws_workflows_active

# Workflow duration P95
histogram_quantile(0.95, rate(adws_workflow_duration_seconds_bucket[5m]))

# Event errors
rate(adws_event_subscriber_errors_total[5m])

# API costs
sum(adws_cost_usd_total)
```

### Grafana

Access Grafana at http://localhost:3000 (admin/admin)

**Available Dashboards**:
- **ADWS Overview**: High-level system health, workflow activity, event metrics, cost tracking
- **Performance Metrics**: Latency analysis, query performance, token usage, heatmaps
- **Resource Utilization**: Pod CPU/memory, Kubernetes metrics, HPA scaling (requires metrics-server)

### Alerts

Alert rules are defined in `monitoring/dashboards/adws_alerts.yml`.

**Active Alerts**:
- Service down (critical)
- High error rate (warning)
- High latency (warning)
- Resource exhaustion (warning)
- High cost rate (warning)

## Environment Variables

Key environment variables for deployment:

```bash
# Deployment
DEPLOYMENT_ENV=production
ROLLBACK_ON_FAILURE=true
DOCKER_REGISTRY=localhost:5000
DOCKER_IMAGE_NAME=phase4b_test

# Kubernetes
K8S_NAMESPACE=phase4b_test
K8S_DEPLOYMENT_NAME=phase4b_test

# Health Checks
HEALTH_CHECK_RETRIES=30
HEALTH_CHECK_INTERVAL=10
```

See `.env.example` for complete list.

## Troubleshooting

### Deployment Fails

```bash
# Check deployment logs
kubectl logs deployment/phase4b_test -n phase4b_test

# Check deployment events
kubectl describe deployment phase4b_test -n phase4b_test

# Check pod status
kubectl get pods -n phase4b_test
```

### Health Check Fails

```bash
# Run manual health check
./scripts/health_check.sh

# Check health endpoint directly
kubectl port-forward -n phase4b_test svc/phase4b_test 8000:8000
curl http://localhost:8000/healthz
```

### Rollback Not Working

```bash
# Check rollout history
kubectl rollout history deployment/phase4b_test -n phase4b_test

# Manual rollback
kubectl rollout undo deployment/phase4b_test -n phase4b_test
```

### Container Restarts

```bash
# Check restart count
kubectl get pods -n phase4b_test

# Check container logs (including previous)
kubectl logs <pod-name> -n phase4b_test --previous
```

## Additional Resources

- [Kubernetes Documentation](k8s/README.md) - Detailed K8s deployment guide
- [Docker Documentation](README.md) - Project README with Docker info
- [Monitoring Guide](MONITORING.md) - Complete guide to Grafana dashboards, metrics, and alerts
- [GitHub Actions Workflows](.github/workflows/) - CI/CD automation and release pipeline

## Support

For issues or questions:
- Check logs: `./scripts/local_dev.sh logs`
- Run health checks: `./scripts/health_check.sh`
- Review K8s events: `kubectl get events -n phase4b_test`

---

*Generated with ADWS UV Cookiecutter v2.0*
