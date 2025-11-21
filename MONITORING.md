# Phase4B Test Project - Monitoring Guide

This guide explains how to monitor your Phase4B Test Project deployment using Prometheus and Grafana.

---

## Table of Contents

1. [Overview](#overview)
2. [Accessing Monitoring Tools](#accessing-monitoring-tools)
3. [Grafana Dashboards](#grafana-dashboards)
4. [Metrics Catalog](#metrics-catalog)
5. [Alert Rules](#alert-rules)
6. [Common Prometheus Queries](#common-prometheus-queries)
7. [Troubleshooting](#troubleshooting)

---

## Overview

Phase4B Test Project includes a complete monitoring stack:

- **Prometheus**: Metrics collection and storage
- **Grafana**: Visualization and dashboards
- **Application Metrics**: Custom metrics from ADWS framework
- **Alert Rules**: Proactive monitoring with 15+ alert definitions

### What's Monitored

- **Workflows**: Execution duration, state transitions, active workflows
- **Events**: Throughput, publish latency, subscriber errors
- **Cost**: LLM API costs by provider, token usage
- **Performance**: Database query latency, event bus performance
- **Health**: Component health status (database, event bus, API)
- **Resources**: CPU, memory, pod status (Kubernetes)

---

## Accessing Monitoring Tools

### Local Development

Start the monitoring stack with Docker Compose:

```bash
# Start all services including Prometheus and Grafana
docker compose up -d

# View logs
docker compose logs -f grafana prometheus
```

**Access Points**:
- **Grafana**: http://localhost:3000
  - Username: `admin`
  - Password: `admin` (change on first login)
- **Prometheus**: http://localhost:9090
- **Application Metrics**: http://localhost:8000/metrics

### Kubernetes Deployment

Port-forward to access monitoring services:

```bash
# Grafana
kubectl port-forward -n phase4b_test svc/grafana 3000:3000

# Prometheus
kubectl port-forward -n phase4b_test svc/prometheus 9090:9090
```

---

## Grafana Dashboards

### 1. ADWS Overview Dashboard

**Purpose**: High-level system health and activity monitoring

**Location**: Dashboards → ADWS → ADWS Overview

**Key Panels**:

1. **Health Status Indicators**
   - Database Health (Green = Healthy, Red = Unhealthy)
   - Event Bus Health
   - Shows real-time component status

2. **Active Workflows**
   - Current number of workflows in progress
   - Gauge with trend graph
   - Helps identify system load

3. **Workflow Activity by State**
   - Time series showing workflow completions by state
   - States: `pending`, `active`, `completed`, `failed`, `cancelled`
   - Rate calculated over 5-minute windows

4. **Event Activity**
   - Event publishing rate by type
   - Event subscriber errors (red line)
   - Helps identify event processing issues

5. **Cost Tracking**
   - Total cost in USD
   - Cost rate (USD/hour)
   - Cost breakdown by provider (Anthropic, OpenAI, Gemini)

6. **Active Alerts**
   - Table showing currently firing alerts
   - Color-coded by severity
   - Links to alert details

**Variables**:
- `datasource`: Prometheus data source
- `interval`: Time aggregation interval (auto, 1m, 5m, 15m, 1h)

**Recommended Time Range**: Last 1 hour (adjustable)

---

### 2. Performance Metrics Dashboard

**Purpose**: Detailed latency analysis and performance troubleshooting

**Location**: Dashboards → ADWS → ADWS Performance

**Key Panels**:

1. **Workflow Duration Percentiles**
   - P50 (median): Typical workflow execution time
   - P95: 95% of workflows complete faster than this
   - P99: Slowest 1% threshold
   - **Interpretation**: P99 > 60s indicates performance issues

2. **Workflow Duration by State**
   - Breaks down latency by workflow state
   - Helps identify which states are slow

3. **Workflow Duration Heatmap**
   - Visual distribution of workflow execution times
   - Hot colors = more workflows at that duration
   - Helps spot performance patterns

4. **Database Query Latency**
   - P95 and P99 query times by query type
   - Query types: `list_workflows`, `get_workflow`, `update_workflow`, `create_workflow`
   - **Alert Threshold**: P95 > 1s

5. **Database Query Rate**
   - Operations per second by query type
   - Helps correlate load with latency

6. **Event Publish Latency**
   - P95/P99 event publishing times by event type
   - **Alert Threshold**: P95 > 100ms

7. **LLM Token Usage**
   - Token consumption rate by provider
   - Split by input/output tokens
   - Stacked area chart shows total usage

8. **Total LLM Tokens**
   - Table showing cumulative token usage
   - Grouped by provider and token type

**Variables**:
- `workflow_id`: Filter by specific workflow (multi-select)
- `provider`: Filter by LLM provider (multi-select)

**Recommended Time Range**: Last 1 hour for real-time, Last 24 hours for trends

---

### 3. Resource Utilization Dashboard

**Purpose**: Kubernetes pod and container resource monitoring

**Location**: Dashboards → ADWS → ADWS Resources

**Prerequisites**:
- Kubernetes metrics-server must be installed
- kube-state-metrics recommended for full functionality

**Key Panels**:

1. **CPU Utilization Gauge**
   - Overall CPU usage percentage
   - Green < 70%, Yellow < 90%, Red >= 90%
   - Calculated against CPU limits

2. **Memory Utilization Gauge**
   - Overall memory usage percentage
   - Same threshold coloring as CPU

3. **CPU Usage by Pod**
   - Time series showing CPU usage per pod
   - Helps identify resource-hungry pods

4. **Memory Usage by Pod**
   - Absolute memory usage in bytes
   - Shows working set memory (actual usage)

5. **Pod Status**
   - Running pods count
   - Color-coded: Green = running, Red = not running

6. **Total Restarts**
   - Sum of pod restart counts
   - Yellow > 1, Red > 5 indicates instability

7. **Pod Restarts Over Time**
   - Step chart showing restart history
   - Helps identify when restarts occurred

8. **Pod Status Table**
   - Lists all pods with their phase
   - Color-coded: Running, Pending, Failed, Succeeded

9. **Network I/O**
   - Receive and transmit rates
   - Transmit shown as negative for clarity

10. **HPA Scaling**
    - Current vs desired replicas
    - Min/max replica limits
    - Shows autoscaling behavior

11. **HPA Metrics Utilization**
    - Metrics that trigger scaling (CPU, memory)
    - Percentage of target threshold

**Variables**:
- `namespace`: Kubernetes namespace (default: phase4b_test)
- `pod`: Filter by pod name (multi-select)

**Recommended Time Range**: Last 1 hour

---

## Metrics Catalog

### Workflow Metrics

```promql
# Workflow execution duration histogram
adws_workflow_duration_seconds{workflow_id, state}
# Buckets: 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, +Inf

# Total workflows by state
adws_workflows_total{state}
# States: pending, active, completed, failed, cancelled

# Currently active workflows
adws_workflows_active
```

**Example Queries**:
```promql
# Average workflow duration over 5 minutes
rate(adws_workflow_duration_seconds_sum[5m]) / rate(adws_workflow_duration_seconds_count[5m])

# Workflow completion rate
rate(adws_workflows_total{state="completed"}[5m])

# Failed workflow percentage
100 * rate(adws_workflows_total{state="failed"}[5m]) / rate(adws_workflows_total[5m])
```

---

### Event Metrics

```promql
# Total events published by type
adws_events_total{event_type}

# Event publish duration histogram
adws_event_publish_duration_seconds{event_type}
# Buckets: 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, +Inf

# Event subscriber errors
adws_event_subscriber_errors_total{event_type, subscriber_id}

# Event throughput gauge
adws_event_throughput_per_second
```

**Example Queries**:
```promql
# Event publishing rate by type
rate(adws_events_total[5m])

# Event error rate
rate(adws_event_subscriber_errors_total[5m])

# P95 event publish latency
histogram_quantile(0.95, rate(adws_event_publish_duration_seconds_bucket[5m]))
```

---

### Cost Metrics

```promql
# Total cost in USD by provider
adws_cost_usd_total{provider}
# Providers: anthropic, openai, gemini

# Cost per workflow
adws_cost_per_workflow_usd{workflow_id, provider}

# LLM token usage
adws_llm_tokens_total{provider, token_type}
# Token types: input, output
```

**Example Queries**:
```promql
# Cost rate in USD per hour
rate(adws_cost_usd_total[1h])

# Average cost per workflow
avg(adws_cost_per_workflow_usd) by (provider)

# Token usage rate
rate(adws_llm_tokens_total[5m])
```

---

### Performance Metrics

```promql
# Database query duration histogram
adws_state_query_duration_seconds{query_type}
# Query types: list_workflows, get_workflow, update_workflow, create_workflow, etc.
# Buckets: 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, +Inf
```

**Example Queries**:
```promql
# P95 query latency
histogram_quantile(0.95, rate(adws_state_query_duration_seconds_bucket[5m]))

# Query rate by type
rate(adws_state_query_duration_seconds_count[5m])
```

---

### Health Metrics

```promql
# Component health status (1 = healthy, 0 = unhealthy)
adws_health_status{component}
# Components: database, event_bus, api
```

**Example Queries**:
```promql
# Check if any component is unhealthy
sum(adws_health_status) < count(adws_health_status)

# Component health status
adws_health_status{component="database"}
```

---

## Alert Rules

All alert rules are defined in `monitoring/dashboards/adws_alerts.yml` and automatically loaded by Prometheus.

### Critical Alerts

| Alert Name | Condition | Duration | Description |
|------------|-----------|----------|-------------|
| **ADWSServiceDown** | `up{job="adws"} == 0` | 1m | ADWS service is not responding |
| **ADWSHighErrorRate** | Error rate > 5% | 5m | More than 5% of workflows failing |
| **ADWSPodNotReady** | Pod not ready | 5m | Kubernetes pod is not in ready state |
| **ADWSDataLoss** | Event persistence failures | 1m | Events are not being persisted |

### Warning Alerts

| Alert Name | Condition | Duration | Description |
|------------|-----------|----------|-------------|
| **ADWSHighLatency** | P95 duration > 60s | 10m | Workflows taking too long |
| **ADWSSlowQueries** | P95 query > 1s | 5m | Database queries are slow |
| **ADWSHighMemoryUsage** | Memory > 90% | 5m | Container memory near limit |
| **ADWSHighCPUUsage** | CPU > 90% | 5m | Container CPU near limit |
| **ADWSHighCostRate** | Cost > $1/hour | 5m | API costs exceeding threshold |
| **ADWSEventBusDelayed** | Event latency > 100ms | 5m | Event processing is slow |

### Info Alerts

| Alert Name | Condition | Duration | Description |
|------------|-----------|----------|-------------|
| **ADWSNoActiveWorkflows** | No workflows for 10m | 10m | System may be idle or stuck |

---

## Common Prometheus Queries

### Workflow Analysis

```promql
# Top 10 slowest workflows
topk(10, adws_workflow_duration_seconds_sum / adws_workflow_duration_seconds_count) by (workflow_id)

# Workflows per minute
rate(adws_workflows_total[1m]) * 60

# Success rate
100 * (
  rate(adws_workflows_total{state="completed"}[5m]) /
  rate(adws_workflows_total[5m])
)
```

### Cost Analysis

```promql
# Cost by provider (last 24 hours)
increase(adws_cost_usd_total[24h])

# Most expensive workflow
topk(5, max(adws_cost_per_workflow_usd) by (workflow_id))

# Token usage trend
deriv(adws_llm_tokens_total[1h])
```

### Performance Debugging

```promql
# Identify slow query types
topk(3, histogram_quantile(0.99, rate(adws_state_query_duration_seconds_bucket[5m]))) by (query_type)

# Event error rate by type
rate(adws_event_subscriber_errors_total[5m]) / rate(adws_events_total[5m])
```

### Resource Monitoring

```promql
# Container memory usage percentage
100 * (
  container_memory_working_set_bytes{namespace="phase4b_test"} /
  container_spec_memory_limit_bytes{namespace="phase4b_test"}
)

# Container CPU usage percentage
100 * rate(container_cpu_usage_seconds_total{namespace="phase4b_test"}[5m]) /
(container_spec_cpu_quota{namespace="phase4b_test"} /
 container_spec_cpu_period{namespace="phase4b_test"})
```

---

## Troubleshooting

### Issue: No Data in Grafana Dashboards

**Symptoms**: All panels show "No data"

**Possible Causes**:
1. Prometheus not scraping the application
2. Application not exposing `/metrics` endpoint
3. Wrong time range selected

**Solutions**:

```bash
# 1. Check if Prometheus is running
docker compose ps prometheus
# or
kubectl get pods -n phase4b_test | grep prometheus

# 2. Verify Prometheus targets
# Open http://localhost:9090/targets
# Ensure "adws" job shows as "UP"

# 3. Check application metrics endpoint
curl http://localhost:8000/metrics

# 4. Verify Prometheus is scraping
# In Prometheus UI, run query:
up{job="adws"}
# Should return 1
```

---

### Issue: Alert Rules Not Loading

**Symptoms**: No alerts visible in Prometheus or Grafana

**Solutions**:

```bash
# 1. Check Prometheus configuration
docker compose exec prometheus cat /etc/prometheus/prometheus.yml
# Verify rule_files section points to /etc/prometheus/dashboards/adws_alerts.yml

# 2. Validate alert rules syntax
docker compose exec prometheus promtool check rules /etc/prometheus/dashboards/adws_alerts.yml

# 3. Restart Prometheus to reload config
docker compose restart prometheus

# 4. Check Prometheus logs
docker compose logs prometheus | grep -i error
```

---

### Issue: High Memory Usage

**Symptoms**: `ADWSHighMemoryUsage` alert firing

**Investigation**:

```promql
# Check current memory usage
container_memory_working_set_bytes{pod=~".*phase4b_test.*"}

# Memory usage trend
rate(container_memory_working_set_bytes{pod=~".*phase4b_test.*"}[5m])

# Active workflows (may cause memory pressure)
adws_workflows_active
```

**Solutions**:
1. Check for memory leaks in application logs
2. Increase pod memory limits in `k8s/deployment.yaml`
3. Scale horizontally with HPA
4. Investigate long-running workflows

---

### Issue: Slow Database Queries

**Symptoms**: `ADWSSlowQueries` alert firing

**Investigation**:

```promql
# Identify slow query types
topk(5, histogram_quantile(0.95, rate(adws_state_query_duration_seconds_bucket[5m]))) by (query_type)

# Query rate by type
rate(adws_state_query_duration_seconds_count[5m]) by (query_type)
```

**Solutions**:
1. Add database indexes for frequently queried fields
2. Optimize query patterns in application code
3. Consider read replicas for list operations
4. Review workflow state management logic

---

### Issue: Grafana Dashboards Not Auto-Loading

**Symptoms**: Dashboards not appearing in Grafana

**Solutions**:

```bash
# 1. Verify dashboard provisioning configuration
docker compose exec grafana cat /etc/grafana/provisioning/dashboards/dashboards.yml

# 2. Check dashboard files exist
docker compose exec grafana ls -la /etc/grafana/provisioning/dashboards/

# 3. Verify Grafana can read files
docker compose exec grafana cat /etc/grafana/provisioning/dashboards/adws_overview.json | jq .

# 4. Check Grafana logs
docker compose logs grafana | grep -i provisioning

# 5. Restart Grafana to reload dashboards
docker compose restart grafana
```

---

### Issue: Metrics Server Not Available (Kubernetes)

**Symptoms**: Resource dashboard shows no pod metrics

**Solutions**:

```bash
# 1. Check if metrics-server is installed
kubectl get deployment metrics-server -n kube-system

# 2. Install metrics-server if missing
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# 3. Verify metrics-server is working
kubectl top nodes
kubectl top pods -n phase4b_test

# 4. Check for kube-state-metrics (optional but recommended)
kubectl get deployment kube-state-metrics -n kube-system
```

---

## Best Practices

### Dashboard Usage

1. **Use Time Range Wisely**
   - Real-time monitoring: Last 15 minutes
   - Troubleshooting: Last 1-6 hours
   - Trend analysis: Last 24 hours - 7 days

2. **Leverage Variables**
   - Filter by specific workflows or providers
   - Use "All" for overview, specific values for debugging

3. **Set Up Alerting**
   - Configure Grafana notifications (email, Slack, etc.)
   - Test alert rules before relying on them

### Query Optimization

1. **Use Appropriate Rate Intervals**
   - Short intervals (1m) for alerts
   - Medium intervals (5m) for dashboards
   - Long intervals (1h) for trends

2. **Avoid Expensive Queries**
   - Limit `topk()` results to 5-10 items
   - Use recording rules for complex calculations
   - Pre-aggregate data where possible

### Retention Management

1. **Prometheus Retention**
   - Default: 15 days (configurable in `prometheus.yml`)
   - Increase for long-term analysis
   - Monitor disk usage

2. **Export Important Data**
   - Use remote write for long-term storage
   - Export dashboards periodically
   - Archive alert history

---

## Additional Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PromQL Cheat Sheet](https://promlabs.com/promql-cheat-sheet/)
- [Phase4B Test Project Deployment Guide](DEPLOYMENT.md)

---

**Need Help?**

If you encounter issues not covered in this guide:
1. Check application logs: `docker compose logs phase4b_test`
2. Review Prometheus targets: http://localhost:9090/targets
3. Consult the [main documentation](README.md)
