# FinOps Agent Helm Chart

A Helm chart for deploying FinOps Agent.

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
- **Password**: `changeme` (or set `GRAFANA_ADMIN_PASSWORD` in values.yaml)

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

## Support

For issues and questions, please refer to the project repository or create an issue in the GitHub repository.
