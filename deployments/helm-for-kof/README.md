# FinOps Agent – Helm Chart for KOF

Deploy FinOps Agent on k0rdent clusters (with KOF) using a Helm chart and k0rdent-native resources.

## Requirements

- k0rdent cluster with KOF enabled
- Prometheus endpoint reachable from FinOps Agent
- Helm 3.10+
- **Grafana Infinity plugin v3.4.1** manually installed in KOF Grafana instance

---

## TL;DR — Package, Push, Deploy

```bash
# From repo root, package the KOF chart
helm package deployments/helm-for-kof

# Optional: push to your OCI registry
export HELM_EXPERIMENTAL_OCI=1
helm push finops-agent-kof-0.1.1.tgz oci://ghcr.io/<org>/charts

# Apply k0rdent resources (HelmRepository, ServiceTemplate, MultiClusterService)
kubectl apply -k deployments/k0rdent-service-template

# Verify ServiceTemplate is valid
kubectl get servicetemplate -n kcm-system
```

## Important Setup Note

The FinOps Agent dashboards require the **Grafana Infinity plugin v3.4.1** to function properly. Since k0rdent/KOF manages Grafana via its own configuration, you'll need to manually install this plugin in your KOF Grafana instance.

To install the plugin in KOF Grafana:
1. Access your KOF Grafana instance
2. Go to Administration → Plugins
3. Search for "Infinity" 
4. Install yesoreyeram-infinity-datasource v3.4.1

Apply the k0rdent resources (HelmRepository, ServiceTemplate, MultiClusterService) here: [k0rdent-service-template](../k0rdent-service-template/README.md)

---

## Customize

Edit `deployments/helm-for-kof/values.yaml` to override defaults (image, Prometheus URL, model settings, Grafana dashboard labels, etc.).

If you pushed to your own registry, update:
- `deployments/k0rdent-service-template/helm-repo.yaml` → `.spec.url`
- `deployments/k0rdent-service-template/service-template.yaml` → `.spec.helm.chartSpec.chart` and `version`


## Upgrade / Uninstall (via Helm, if installing directly)

```bash
# Upgrade
helm upgrade --install finops-agent oci://ghcr.io/<org>/charts/finops-agent-kof -n finops

# Uninstall
helm uninstall finops-agent -n finops
```

## Support

Open an issue in the project repository.
