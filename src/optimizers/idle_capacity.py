import numpy as np
from collections import defaultdict
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class IdleCapacityOptimizer:
    """ Generate cost-saving recommendations based on idle capacity.

    Parameters
    ----------
    config : dict
        Optional configuration allowing thresholds to be tuned at runtime.
        Keys:
        * ``idle_cpu_threshold`` (float, default 0.30) – minimum *average* idle
          CPU fraction (e.g. 0.30 = 30 %) required to trigger a recommendation.
        * ``idle_mem_threshold`` (float, default 0.30) – analogous for memory.
        * ``min_node_savings`` (int, default 1) – minimum nodes that must be
          removable to bother reporting.
    """
    def __init__(self, config: Dict[str, Any] | None = None):
        cfg = config or {}
        self.idle_cpu_th = float(cfg.get("idle_cpu_threshold", 0.30))
        self.idle_mem_th = float(cfg.get("idle_mem_threshold", 0.30))
        self.min_node_savings = int(cfg.get("min_node_savings", 1))

    def optimise(self, forecast_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        recs: List[Dict[str, Any]] = []
        for cluster, data in forecast_dict.items():
            if cluster.startswith("_"):
                continue
            try:
                recs += self._analyse_cluster(cluster, data["forecasts"])
            except Exception as e:
                logger.warning("Error on %s: %s", cluster, e)
        return recs

    def _analyse_cluster(self, cluster: str, forecasts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Group data per node
        node_data = defaultdict(lambda: {"cpu_idle": [], "mem_idle": [], "cost": []})
        # also capture one set of timestamps to compute horizon
        ts_list = None

        for e in forecasts:
            m = e["metric"]
            if m.get("quantile") not in ("0.50", "0.5", None):
                continue
            name = m["__name__"]
            node = m["node"]
            if "cp" in node:            # skip control‐plane
                continue
            vals = e.get("values", [])
            if not vals:
                continue
            last = vals[-1]

            if name.startswith("cpu_pct_per_node"):
                node_data[node]["cpu_idle"].append(max(0, 100 - last))
            elif name.startswith("mem_pct_per_node"):
                node_data[node]["mem_idle"].append(max(0, 100 - last))
            elif name.startswith("cost_usd_per_node"):
                node_data[node]["cost"].append(last)

            if ts_list is None and e.get("timestamps"):
                ts_list = e.get("timestamps")

        if not ts_list:
            return []

        # Compute horizon in days
        horizon_sec = (ts_list[-1] - ts_list[0]) / 1000.0
        horizon_days = round(horizon_sec / (3600 * 24))
        if horizon_days <= 0:
            return []

        # Find candidate nodes
        candidates: Dict[str, float] = {}
        for node, d in node_data.items():
            if not d["cpu_idle"] or not d["mem_idle"] or not d["cost"]:
                continue
            avg_cpu = np.mean(d["cpu_idle"]) / 100.0
            avg_mem = np.mean(d["mem_idle"]) / 100.0
            if avg_cpu >= self.idle_cpu_th and avg_mem >= self.idle_mem_th:
                # average hourly cost → daily → total horizon
                hr_cost = np.mean(d["cost"])
                daily_cost = hr_cost * 24
                total_savings = daily_cost * horizon_days
                candidates[node] = total_savings

        if not candidates:
            return []
        worker_node_count = len(node_data)
        if worker_node_count <= 1:
            return []
        # Respect minimum removable nodes threshold
        if len(candidates) < self.min_node_savings:
            return []

        # Pick the best node to remove
        node_to_drop, savings = max(candidates.items(), key=lambda kv: kv[1])
        if savings <= 0:
            return []

        rec = {
            "cluster": cluster,
            "type": "idle_capacity",
            "node_to_remove": node_to_drop,
            "forecast_horizon_days": horizon_days,
            "estimated_savings_usd": round(savings, 2),
            "message": (
                f"Over the {horizon_days}-day forecast, removing node "
                f"'{node_to_drop}' could save approximately "
                f"${savings:,.2f}."
            )
        }
        return [rec]