# Phase4B Test Project - Kubernetes Deployment

This directory contains Kubernetes manifests for deploying Phase4B Test Project to a Kubernetes cluster.

## Overview

The deployment includes:

- **Namespace**: Isolated environment for the application
- **ConfigMap**: Non-sensitive configuration
- **Secret**: Sensitive data (API keys, passwords)
- **Deployment**: Application pods with rolling updates
- **Service**: Internal load balancing
- **Ingress**: External HTTP/HTTPS access
- **HPA**: Horizontal Pod Autoscaler for automatic scaling
- **PVC**: Persistent storage for stateful data

## Prerequisites

### Required

1. **Kubernetes Cluster** (one of):
   - Local: [minikube](https://minikube.sigs.k8s.io/), [kind](https://kind.sigs.k8s.io/), [k3s](https://k3s.io/), [Docker Desktop](https://www.docker.com/products/docker-desktop)
   - Cloud: GKE, EKS, AKS, DigitalOcean Kubernetes

2. **kubectl** v1.14+
   ```bash
   kubectl version --client
   ```

3. **Docker Image** built and pushed to registry
   ```bash
   docker build -t localhost:5000/phase4b_test:latest .
   docker push localhost:5000/phase4b_test:latest
   ```

### Optional

1. **Metrics Server** (for HPA)
   ```bash
   kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
   ```

2. **Ingress Controller** (for external access)
   ```bash
   # NGINX Ingress Controller
   kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml

   # OR Traefik
   helm repo add traefik https://traefik.github.io/charts
   helm install traefik traefik/traefik
   ```

3. **Kustomize** (built into kubectl 1.14+)
   ```bash
   kubectl kustomize --help
   ```

## Quick Start

### 1. Create Secrets

Copy the example secret file and fill in your API keys:

```bash
cp k8s/secret.yaml.example k8s/secret.yaml
```

Edit `k8s/secret.yaml` and replace placeholder values with base64-encoded secrets:

```bash
# Encode your API keys
echo -n "sk-your-openai-key" | base64
echo -n "sk-ant-your-anthropic-key" | base64
```

**IMPORTANT**: Never commit `k8s/secret.yaml` to version control!

### 2. Deploy Using Kustomize (Recommended)

```bash
# Preview what will be deployed
kubectl kustomize k8s/

# Apply all manifests
kubectl apply -k k8s/

# Apply secrets separately (not in kustomization.yaml)
kubectl apply -f k8s/secret.yaml
```

### 3. Deploy Manually (Alternative)

```bash
# Create namespace
kubectl apply -f k8s/namespace.yaml

# Create secrets and config
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/configmap.yaml

# Deploy application
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Optional: External access
kubectl apply -f k8s/ingress.yaml

# Optional: Autoscaling
kubectl apply -f k8s/hpa.yaml
```

### 4. Verify Deployment

```bash
# Check namespace
kubectl get ns phase4b_test

# Check all resources
kubectl get all -n phase4b_test

# Check deployment status
kubectl rollout status deployment/phase4b_test -n phase4b_test

# View pods
kubectl get pods -n phase4b_test

# Check logs
kubectl logs -f deployment/phase4b_test -n phase4b_test

# Check HPA (if metrics server installed)
kubectl get hpa -n phase4b_test
kubectl top pods -n phase4b_test
```

## Accessing the Application

### Internal Access (from within cluster)

```bash
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n phase4b_test -- \
  curl http://phase4b_test.phase4b_test.svc.cluster.local:8000/healthz
```

### Port Forward (local development)

```bash
kubectl port-forward -n phase4b_test svc/phase4b_test 8000:8000
```

Then access: http://localhost:8000

### Ingress (external access)

If you deployed the ingress:

```bash
# Get ingress details
kubectl get ingress -n phase4b_test

# For local development, add to /etc/hosts:
# <INGRESS_IP> phase4b_test.local
```

Access: http://phase4b_test.local

## Configuration

### Update ConfigMap

Edit `k8s/configmap.yaml` and apply:

```bash
kubectl apply -f k8s/configmap.yaml -n phase4b_test

# Restart pods to pick up changes
kubectl rollout restart deployment/phase4b_test -n phase4b_test
```

### Update Secrets

```bash
# Update base64-encoded values in k8s/secret.yaml
kubectl apply -f k8s/secret.yaml -n phase4b_test

# Restart pods
kubectl rollout restart deployment/phase4b_test -n phase4b_test
```

### Scale Replicas

```bash
# Manual scaling
kubectl scale deployment/phase4b_test --replicas=3 -n phase4b_test

# Or edit deployment.yaml and apply
```

### Update Image

```bash
# Using kustomize
cd k8s/
kubectl kustomize edit set image localhost:5000/phase4b_test=localhost:5000/phase4b_test:v1.2.3
kubectl apply -k .

# Or directly
kubectl set image deployment/phase4b_test \
  phase4b_test=localhost:5000/phase4b_test:v1.2.3 \
  -n phase4b_test
```

## Rollback

### Rollback Deployment

```bash
# View rollout history
kubectl rollout history deployment/phase4b_test -n phase4b_test

# Rollback to previous version
kubectl rollout undo deployment/phase4b_test -n phase4b_test

# Rollback to specific revision
kubectl rollout undo deployment/phase4b_test --to-revision=2 -n phase4b_test
```

## Monitoring

### View Logs

```bash
# All pods
kubectl logs -f deployment/phase4b_test -n phase4b_test

# Specific pod
kubectl logs -f <pod-name> -n phase4b_test

# Previous container logs (if pod crashed)
kubectl logs <pod-name> -n phase4b_test --previous
```

### Resource Usage

```bash
# Node resources
kubectl top nodes

# Pod resources
kubectl top pods -n phase4b_test

# Describe pod
kubectl describe pod <pod-name> -n phase4b_test
```

### Health Checks

```bash
# Check health endpoint via port-forward
kubectl port-forward -n phase4b_test svc/phase4b_test 8000:8000 &
curl http://localhost:8000/healthz
```

## Troubleshooting

### Pods Not Starting

```bash
# Check pod status
kubectl get pods -n phase4b_test

# Describe pod
kubectl describe pod <pod-name> -n phase4b_test

# Check logs
kubectl logs <pod-name> -n phase4b_test

# Common issues:
# - Image pull errors: Check registry credentials
# - Secret missing: Verify k8s/secret.yaml is applied
# - Resource limits: Check node capacity
```

### HPA Not Scaling

```bash
# Verify metrics server
kubectl get deployment metrics-server -n kube-system

# Check HPA status
kubectl describe hpa phase4b_test -n phase4b_test

# Verify resource requests are defined in deployment
kubectl get deployment phase4b_test -n phase4b_test -o yaml | grep -A 5 resources
```

### Ingress Not Working

```bash
# Check ingress controller
kubectl get pods -n ingress-nginx  # or your ingress namespace

# Check ingress resource
kubectl describe ingress phase4b_test -n phase4b_test

# Verify service endpoints
kubectl get endpoints phase4b_test -n phase4b_test
```

## Cleanup

### Delete Application (keep namespace)

```bash
# Using kustomize
kubectl delete -k k8s/ --ignore-not-found=true

# Manually
kubectl delete deployment,service,ingress,hpa,configmap -n phase4b_test --all
```

### Delete Everything (including namespace)

```bash
kubectl delete namespace phase4b_test
```

## Production Recommendations

1. **Resource Limits**: Adjust CPU/memory in `deployment.yaml` based on load testing
2. **Storage**: Configure appropriate `StorageClass` for your cluster
3. **Secrets Management**: Use [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) or [External Secrets](https://external-secrets.io/)
4. **Monitoring**: Integrate with Prometheus/Grafana
5. **Logging**: Configure log aggregation (ELK, Loki)
6. **Backup**: Regular backups of PVC data
7. **HTTPS**: Configure TLS certificates in `ingress.yaml`
8. **Network Policies**: Add network policies for security
9. **Pod Security**: Enable Pod Security Standards
10. **CI/CD**: Automate deployments with GitOps (ArgoCD, Flux)

## Additional Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [kubectl Cheat Sheet](https://kubernetes.io/docs/reference/kubectl/cheatsheet/)
- [Kustomize Documentation](https://kubectl.docs.kubernetes.io/references/kustomize/)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/configuration/overview/)
