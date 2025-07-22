# FinOps Agent – Helm Chart

Deploy **FinOps Agent** on k0rdent clusters (with KOF).

## Requirements

* k0rdent cluster with KOF enabled  
* Prometheus endpoint reachable from FinOps Agent  
* Helm 3.10 +

---

## TL;DR — Quick Install

```bash
helm repo add finops-agent <repo-url>
helm repo update
helm install finops-agent finops-agent/finops-agent \
  --namespace finops --create-namespace
```

The chart:

* Installs **FinOps Agent** in **`finops`**  
* Adds an **Infinity** datasource in **`finops`**  
* Publishes the **Forecasting Dashboard** to Grafana in **`kof`**

> **Why two namespaces?**  
> KOF conventionally hosts Grafana and shared dashboards in `kof`; FinOps Agent and its datasource live with your workloads in `finops`.

---

## What You Get

| Component | Purpose |
|-----------|---------|
| **FinOps Agent** | Scrapes Prometheus, runs TOTO models, emits forecast metrics |
| **Grafana Datasource** | Connects Grafana to FinOps Agent’s `/metrics` API |
| **Forecasting Dashboard** | Visualises cost & resource forecasts at node and cluster level |

Key panels include: hourly cost, CPU / memory utilisation, node count, and optimisation hints—each at **node** and **cluster** granularity.


## Common Tasks

### Upgrade

```bash
helm upgrade finops-agent finops-agent/finops-agent \
  --namespace finops
```

### Uninstall

```bash
helm uninstall finops-agent -n finops
```

---

## Customising

Create `values.yaml` to override defaults.

Then:

```bash
helm upgrade --install finops-agent finops-agent/finops-agent \
  -f values.yaml -n finops
```

---

## Support  

Open an issue in the [GitHub repo](https://github.com/ramessesii2/mr-finops-agent).