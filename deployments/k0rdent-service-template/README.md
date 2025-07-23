# Deploy FinOps Agent with k0rdent Native Resources

This folder gives you three YAMLs that let you roll out **FinOps Agent** to any
KOF‑enabled (k0rdent‑managed) cluster.

## How It Works

| CRD                | File                                | Purpose |
|--------------------|-------------------------------------|---------|
| `HelmRepository`   | `helm-repo.yaml`                    | Registers an OCI Helm repo that hosts your FinOps Agent chart. |
| `ServiceTemplate`  | `service-template.yaml`             | Points to that chart (`finops-agent-kof v0.1.0`). |
| `MultiClusterService` | `beach-head-mcs.yaml`            | Selects target clusters (by label) and deploys the ServiceTemplate into **`kcm-system`** on each. |

**Flow**

1. Flux pulls the chart from your OCI registry.  
2. k0rdent's `MultiClusterService`, matches clusters, and installs FinOps Agent referenced via `ServiceTemplate`.  
3. Grafana (shipped in KOF) discovers the datasource + dashboards bundled in the chart.

## Quick Start

```bash
# 1. Add the Helm repo so Flux can fetch your chart
kubectl apply -f helm-repo.yaml
```
```bash
# 2. Register the ServiceTemplate
kubectl apply -f service-template.yaml
```
**Wait for the finops-agent-0-1-0 servicetemplate to become `VALID: true`**
```bash
kubectl get servicetemplate -n kcm-system
```

```bash
# 3. Deploy FinOps Agent on the mothership k0rdent
kubectl apply -f beach-head-mcs.yaml
```

Clusters labelled:

```yaml
k0rdent.mirantis.com/management-cluster: "true"
sveltos-agent: present
```

will immediately receive FinOps Agent in namespace `kcm-system`.

## Swap In Your Own Chart

1. Push your chart to any OCI registry, e.g.  
   `ghcr.io/<org>/charts/finops-agent:1.2.3`.
2. Edit **`helm-repo.yaml`** – change `.spec.url` to your registry.
3. Edit **`service-template.yaml`** – update `.spec.helm.chartSpec.chart`
   and `.version`.
4. Re‑apply both manifests – Flux will pull the new chart and KCM upgrades
   every cluster automatically.
