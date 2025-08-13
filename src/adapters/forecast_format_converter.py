"""Convert TOTO forecast output to cluster-grouped Prometheus format."""
import logging
from typing import Dict, Any, List, Optional


class ForecastFormatConverter:
    """Convert TOTO forecast output to cluster-grouped format."""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def _get_forecast_name(self, metric_name: str) -> str:
        """Generate forecast metric name by appending _forecast suffix."""
        return f"{metric_name}_forecast"
    
    def convert_to_cluster_grouped_format(
        self,
        toto_forecast_output: Dict[str, Any],
        cluster_name: str,
        node_name: Optional[str] = None,
        extra_labels: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Convert TOTO forecast output to cluster-grouped Prometheus format.
        
        Args:
            toto_forecast_output: TOTO forecast output from TOTOAdapter.forecast()
            cluster_name: Name of the cluster for labeling
            node_name: Optional node name (defaults to "aggregated")
            extra_labels: Optional additional labels to include
            
        Returns:
            List of Prometheus-style forecast entries in the format:
            [
                {
                    "metric": {
                        "__name__": "cpu_usage_forecast",
                        "clusterName": "prod-eu1",
                        "node": "ip-10-0-3-42",
                        "quantile": "0.50",
                        "horizon": "7d"
                    },
                    "values": [0.27, 0.29, 0.31],
                    "timestamps": [1719955200000, 1719958800000, 1719962400000]
                },
                ...
            ]
        """
        if not toto_forecast_output:
            raise ValueError("Empty TOTO forecast output provided")
        
        if not cluster_name:
            raise ValueError("Cluster name is required")
        
        series_results = toto_forecast_output.get('series', {})
        timestamps = toto_forecast_output.get('timestamps', [])
        variate_metadata = toto_forecast_output.get('variate_metadata', [])
        horizon = toto_forecast_output.get('horizon', 0)
        
        if not series_results or not timestamps:
            self.logger.error(f"VALIDATION FAILED - series_results: {bool(series_results)}, timestamps: {bool(timestamps)}")
            raise ValueError("Invalid TOTO forecast output format")
        
        if variate_metadata:
            unique_metrics = set()
            for metadata in variate_metadata:
                unique_metrics.add(metadata['metric_name'])
            metric_names = list(unique_metrics)
        else:
            raise ValueError("No variate_metadata found in TOTO forecast output")
        
        cluster_forecasts = []
        node_name = node_name or "aggregated"
        extra_labels = extra_labels or {}
        
        # Convert each metric and quantile combination
        if variate_metadata:
            # Process variate_id-based series structure (renamed from quantiles for clarity)
            for variate_id, variate_data in series_results.items():
                if 'metadata' not in variate_data or 'quantiles' not in variate_data:
                    self.logger.warning(f"Invalid variate data for {variate_id}")
                    continue
                
                metadata = variate_data['metadata']
                metric_name = metadata['metric_name']
                variate_quantiles = variate_data['quantiles']
                
                forecast_name = self._get_forecast_name(metric_name)
                
                # Create forecast entry for each quantile
                for quantile_key, quantile_values in variate_quantiles.items():
                    if not isinstance(quantile_values, list) or len(quantile_values) != len(timestamps):
                        self.logger.warning(f"Invalid quantile values for {variate_id} {quantile_key}")
                        continue
                    
                    # Extract quantile value from key (e.g., "q0.50" -> "0.50")
                    quantile_str = quantile_key.replace('q', '')
                    
                    metric_labels = {
                        "__name__": forecast_name,
                        "clusterName": cluster_name,
                        "node": metadata.get('node_name', node_name),
                        "quantile": quantile_str,
                        "horizon": f"{horizon//24}d" if horizon >= 24 else f"{horizon}h"
                    }
                    
                    metric_labels.update(extra_labels)
                    
                    processed_values = self._process_values_for_metric_type(metric_name, quantile_values)
                    
                    forecast_entry = {
                        "metric": metric_labels,
                        "values": processed_values,
                        "timestamps": timestamps
                    }
                    
                    cluster_forecasts.append(forecast_entry)

        if not cluster_forecasts:
            raise ValueError(f"No valid forecast entries generated for cluster: {cluster_name}")
        
        self.logger.debug(f"Generated {len(cluster_forecasts)} forecast entries for cluster: {cluster_name}")
        return cluster_forecasts
    
    def _process_values_for_metric_type(self, metric_name: str, values: List[float]) -> List[float]:
        """Process values based on metric type - all our metrics are positive-only."""
        # All our metrics are positive-only (costs, percentages, counts, memory)
        # Only node_count and cpu_total_cores need integer rounding
        if 'count' in metric_name or 'cores' in metric_name:
            return [max(0, round(value)) for value in values]
        else:
            return [max(0.0, round(value, 6)) for value in values]
