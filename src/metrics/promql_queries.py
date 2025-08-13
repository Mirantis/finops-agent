"""PromQL query configuration for forecasting agent."""
from typing import Dict

CLUSTER_QUERIES = {
    "cost_usd_per_cluster": "sum(node_total_hourly_cost) by (cluster)",
    "cpu_pct_per_cluster": "100 * (1 - avg by (cluster) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])))",
    "mem_pct_per_cluster": "100 * (1 - avg by (cluster) (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))",
    "node_count_per_cluster": "count by (cluster) (kube_node_status_condition{condition=\"Ready\",status=\"true\"})",
    "mem_total_gb_per_cluster": "sum by (cluster) (node_memory_MemTotal_bytes) / 1024 / 1024 / 1024",
}

NODE_QUERIES = {
    "cost_usd_per_node": "sum by (cluster, node) (node_total_hourly_cost)",
    "cpu_pct_per_node": "100 * (1 - avg by (cluster, instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])))",
    "mem_pct_per_node": "100 * (1 - avg by (cluster, instance) (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))",
    "cpu_total_cores_per_node": "sum by (cluster, instance) (machine_cpu_cores)",
}

def get_all_queries() -> Dict[str, str]:
    """Get all PromQL queries."""
    return {**CLUSTER_QUERIES, **NODE_QUERIES}
