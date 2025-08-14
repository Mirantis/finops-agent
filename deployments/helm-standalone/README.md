# FinOps Agent Helm Chart

A Helm chart for deploying FinOps Agent - a Financial Operations Forecasting Agent that provides cost optimization and forecasting capabilities for Kubernetes clusters.

## Overview

FinOps Agent is a forecasting application that:

- Collects metrics from Prometheus
- Uses TOTO models for forecasting
- Provides cost optimization recommendations
- Exposes metrics for monitoring

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- Access to a Prometheus instance

## Installation

### Add the repository

```bash
helm repo add finops-agent <repository-url>
helm repo update
```

### Install the chart

```bash
# Install with default values
helm install finops-agent .

# Install with custom values
helm install finops-agent . -f custom-values.yaml

# Install in a specific namespace
helm install finops-agent . --namespace finops --create-namespace
```

## Configuration

The following table lists the configurable parameters and their default values:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicaCount` | Number of replicas | `1` |
| `image.repository` | Image repository | `ramessesii/finops-agent` |
| `image.tag` | Image tag | `latest` |
| `image.pullPolicy` | Image pull policy | `Always` |
| `service.type` | Service type | `ClusterIP` |
| `service.port` | Service port | `8081` |
| `config.collector.url` | Prometheus URL | `http://kof-mothership-promxy.kof.svc.cluster.local:8082` |
| `config.collector.lookback_days` | Data lookback period | `7` |
| `config.models.type` | Model type | `toto` |
| `config.models.forecast_horizon` | Forecast horizon in days | `7` |
| `resources` | Resource limits and requests | `{}` |
| `nodeSelector` | Node selector | `{}` |
| `tolerations` | Tolerations | `[]` |
| `affinity` | Affinity rules | `{}` |

## Examples

### Basic Installation

```bash
helm install my-finops-agent .
```

### Installation with Custom Configuration

```bash
helm install finops-agent . \
  --set replicaCount=2 \
  --set config.collector.url=http://my-prometheus:9090 \
  --set resources.requests.cpu=200m \
  --set resources.requests.memory=512Mi \
  --set resources.limits.cpu=2000m \
  --set resources.limits.memory=4Gi
```

## Grafana Dashboard

This Helm chart includes a bundled Grafana instance with pre-configured dashboards for FinOps forecasting visualization.

### Accessing Grafana

#### 1. Deploy with Grafana Enabled (Default)

```bash
# Grafana is enabled by default
helm install finops-agent .

# Or explicitly enable Grafana
helm install finops-agent . --set grafana.enabled=true
```

#### 2. Port Forward to Access Grafana UI

```bash
# Forward local port 3001 to Grafana service port 3001
kubectl port-forward service/finops-agent-grafana 3001:3001
```

#### 3. Access Dashboard

- **URL**: http://localhost:3001
- **Username**: `admin`
- **Password**: `finops123`

### Dashboard Overview

The **Forecasting Dashboard** provides comprehensive visualization of:

**Node-Level Forecasts:**

- Node Hourly Cost Forecast
- Node CPU Cores Forecast
- Node CPU Utilisation Forecast
- Node Memory Utilisation Forecast

**Cluster-Level Forecasts:**

- Cluster Hourly Cost Forecast
- Cluster CPU Utilisation Forecast
- Cluster Memory Utilisation Forecast
- Node Count Per Cluster Forecast
- Total Memory Utilization Per Cluster Forecast

### Grafana Configuration

| Parameter | Description | Default |
|-----------|-------------|----------|
| `grafana.enabled` | Enable/disable Grafana | `true` |
| `grafana.image.repository` | Grafana image repository | `grafana/grafana` |
| `grafana.image.tag` | Grafana image tag | `10.4.7` |
| `grafana.service.port` | Grafana service port | `3001` |
| `grafana.config.security.admin_user` | Admin username | `admin` |
| `grafana.config.security.admin_password` | Admin password | `finops123` |

## Monitoring

The application exposes metrics on `/metrics` endpoint (port 8081 by default). You can configure Prometheus to scrape these metrics:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: finops-agent
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: finops-agent
  endpoints:
  - port: metrics
    path: /metrics
```

## Upgrading

```bash
helm upgrade finops-agent .
```

## Uninstalling

```bash
helm uninstall finops-agent
```

## Troubleshooting

### Check pod status

```bash
kubectl get pods -l app.kubernetes.io/name=finops-agent
```

### View logs

```bash
kubectl logs -f deployment/finops-agent
```

### Check configuration

```bash
kubectl get configmap finops-agent-config -o yaml
```

## Support

For issues and questions, please refer to the project repository or create an issue in the GitHub repository.
