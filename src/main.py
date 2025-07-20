import logging
from typing import Dict, Any, Optional, List
import yaml
from datetime import datetime, timedelta, timezone
import time
from darts import TimeSeries
import json
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from collectors.prometheus import PrometheusCollector
from optimizers.idle_capacity import IdleCapacityOptimizer
from adapters.forecasting.nbeats_adapter import NBEATSAdapter
from adapters.forecasting.toto_adapter import TOTOAdapter
from adapters.prometheus_toto_adapter import PrometheusToTotoAdapter
from adapters.prometheus_timeseries_adapter import PrometheusTimeseriesAdapter
from adapters.forecast_format_converter import ForecastFormatConverter
from validation.forecast_validator import ForecastValidator
from metrics.metric_types import MetricTypeClassifier, MetricAggregationLevel
from metrics.promql_queries import get_all_queries

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PROMQL = get_all_queries()

exported_forecasts: Dict[str, Dict[str, Any]] = {}
active_clusters: set = set()

def _start_forecast_server(host: str, port: int):
    """Start a background HTTP server exposing forecast JSON."""

    class _Handler(BaseHTTPRequestHandler):
        def _send_json(self, data, status=200):
            body = json.dumps(data).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                logger.warning("Connection to client lost while sending response")
            except Exception as exc:
                logger.error(f"Failed to send HTTP response: {exc}")
        
        def _handle_model_stats_endpoint(self):
            try:
                validation_results = exported_forecasts.get('_validation_results')
                
                if not validation_results:
                    self._send_json({
                        "status": "no_validation_data",
                        "message": "No validation data available. Validation may not have run yet.",
                        "timestamp": datetime.now().isoformat()
                    })
                    return
                
                if not isinstance(validation_results, dict):
                    self._send_json({
                        "status": "error",
                        "message": "Validation data is malformed",
                        "timestamp": datetime.now().isoformat()
                    })
                    return
                
                summary = self._calculate_validation_summary(validation_results)
                
                self._send_json({
                    "status": "success",
                    "timestamp": datetime.now().isoformat(),
                    "validation_results": validation_results,
                    "summary": summary,
                    "validation_config": {
                        "train_ratio": 0.7,
                        "metrics": ["mape", "mae", "rmse"],
                        "format": "toto"
                    }
                })
                
            except Exception as e:
                self._send_json({
                    "status": "error",
                    "message": f"Error processing validation data: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }, status=500)
        
        def _calculate_validation_summary(self, validation_results):
            cluster_count = len(validation_results)
            clusters_with_errors = 0
            total_metrics = 0
            mape_values = []
            
            for cluster_name, cluster_data in validation_results.items():
                if isinstance(cluster_data, dict):
                    if "error" in cluster_data:
                        clusters_with_errors += 1
                    else:
                        # Count valid metrics and collect MAPE values
                        for metric_name, metric_data in cluster_data.items():
                            if isinstance(metric_data, dict) and "mape" in metric_data:
                                total_metrics += 1
                                if isinstance(metric_data["mape"], (int, float)):
                                    mape_values.append(metric_data["mape"])
            
            average_mape = sum(mape_values) / len(mape_values) if mape_values else 0
            
            return {
                "cluster_count": cluster_count,
                "clusters_with_errors": clusters_with_errors,
                "metrics_validated": total_metrics,
                "average_mape": round(average_mape, 2)
            }

        def do_GET(self):
            if self.path == "/clusters" or self.path == "/clusters/":
                cluster_list = list(active_clusters)
                self._send_json({
                    "clusters": cluster_list,
                    "count": len(cluster_list)
                })
            elif self.path == "/metrics" or self.path == "/metrics/":
                # Filter out internal keys from metrics response
                cluster_metrics = {k: v for k, v in exported_forecasts.items() if not k.startswith('_')}
                self._send_json({
                    "metrics": cluster_metrics,
                    "clusters_count": len(active_clusters),
                    "total_forecast_entries": sum(len(forecasts) if isinstance(forecasts, list) else 1 
                                                 for forecasts in cluster_metrics.values())
                })
            elif self.path in ("/stats", "/stats/"):
                 # Return validation results and model information
                 self._handle_model_stats_endpoint()
            elif self.path in ("/optimize", "/optimize/"):
                 # Generate optimisation recommendations on demand
                 try:
                     recs = exported_forecasts['_recommendations']
                     self._send_json({
                         "status": "success",
                         "recommendations": recs,
                         "generated_at": datetime.now().isoformat()
                     })
                 except Exception as exc:
                     logger.error("Optimizer error: %s", exc)
                     self._send_json({"status": "error", "message": str(exc)}, status=500)
            elif self.path.startswith("/metrics/"):
                # Return metrics for specific cluster
                cluster = self.path[len("/metrics/"):]
                if cluster in active_clusters and cluster in exported_forecasts:
                    cluster_forecasts = exported_forecasts[cluster]
                    self._send_json(cluster_forecasts)
                else:
                    self._send_json({"error": f"cluster '{cluster}' not found", "available_clusters": list(active_clusters)}, status=404)
            else:
                # Health check or default endpoint
                self._send_json({
                    "message": "Forecasting Agent API",
                    "status": "running",
                    "endpoints": {
                        "/clusters": "List all available clusters",
                        "/metrics": "Get all metrics from all clusters",
                        "/metrics/{clusterName}": "Get forecasts for specific cluster",
                        "/stats": "Validation results",
                        "/optimize": "Generate optimisation recommendations"
                    },
                    "active_clusters": len(active_clusters)
                })

        def log_message(self, *args, **kwargs):
            return

    server = ThreadingHTTPServer((host, port), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Forecast HTTP server running on {host}:{port}")

class ForecastingAgent:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.collector = self._init_collector()
        self.optimizer = self._init_optimizer()

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _init_collector(self) -> PrometheusCollector:
        return PrometheusCollector(self.config['collector'])

    def _init_optimizer(self) -> IdleCapacityOptimizer:
        return IdleCapacityOptimizer(self.config['optimizer'])

    def collect_raw_metrics(self) -> Dict[str, Any]:
        """Collect raw metrics from Prometheus."""
        try:
            end_time = datetime.now(tz=timezone.utc)
            scrape_step = self.config['collector'].get('step', '5m')
            start_time = end_time - timedelta(days=self.config['collector'].get('lookback_days', 4))
            # Get raw results from PrometheusCollector
            return self.collector.collect_metrics_timeseries(start_time, end_time, PROMQL)
        except Exception as e:
            logger.error(f"Error collecting raw metrics: {str(e)}")
            raise
    
    def convert_to_timeseries(self, raw_results: Dict[str, Any]) -> Dict[str, TimeSeries]:
        """Convert raw Prometheus results to per-cluster TimeSeries."""
        try:
            freq = self.config['models'].get('freq', "h")
            return PrometheusTimeseriesAdapter.prometheus_results_to_timeseries(raw_results, freq=freq)
        except Exception as e:
            logger.error(f"Error converting to timeseries: {str(e)}")
            raise
    
    def collect_metrics_timeseries(self) -> Dict[str, TimeSeries]:
        """Collect metrics and convert to TimeSeries (convenience method)."""
        raw_results = self.collect_raw_metrics()
        return self.convert_to_timeseries(raw_results)

    def generate_forecast_NBEATS(self, series: TimeSeries) -> dict:
        """Generate NBEATS forecast with horizon calculation and JSON formatting."""
        try:
            step = self.config['collector'].get('step', 'h')
            horizon_days = self.config['models'].get('forecast_horizon', 30)
            if step in ['h', '1h', 'hour']:
                horizon = horizon_days * 24
            elif step in ['m', '1m', 'min']:
                horizon = horizon_days * 24 * 60
            else:
                horizon = horizon_days
                
            model_config = self.config['models'].get('nbeats', {})
            adapter = NBEATSAdapter(model_config)
            adapter.fit(series)
            
            likelihood = model_config.get('likelihood', None)
            num_samples = model_config.get('num_samples', 100) if likelihood else 1
            quantiles = self.config['models'].get('quantiles', [0.1, 0.5, 0.9])
            
            # Use adapter's forecast method with quantiles for JSON formatting
            return adapter.forecast(horizon, num_samples=num_samples, quantiles=quantiles)
        except Exception as e:
            logger.error(f"Error generating NBEATS forecast: {str(e)}")
            raise

    def generate_forecast_TOTO(self, raw_results: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """Generate TOTO forecast for all clusters
        - PrometheusToTotoAdapter: converts raw JSON to MaskedTimeseries tensors
        - TOTOAdapter.forecast(): forecasting logic
        - ForecastFormatConverter: transforms TOTO output to cluster-grouped format
        
        Args:
            raw_results: Raw Prometheus query results containing data for all clusters
            
        Returns:
            Dict with cluster-grouped format: {
                cluster_name: [
                    {
                        "metric": {
                            "__name__": "cpu_usage_forecast",
                            "clusterName": "prod-eu1",
                            "node": "aggregated",
                            "quantile": "0.50",
                            "horizon": "7d"
                        },
                        "values": [0.27, 0.29, 0.31],
                        "timestamps": [1719955200000, 1719958800000, 1719962400000]
                    },
                    ...
                ]
            }
        """
        try:
            # Convert raw Prometheus JSON to multi-cluster tensors
            prometheus_to_toto = PrometheusToTotoAdapter()
            
            # Extract cluster names from raw results
            cluster_names = self._extract_cluster_names_from_raw_results(raw_results)
            if not cluster_names:
                raise ValueError("No clusters found in raw Prometheus results")
            
            # Convert each cluster individually using the existing single-cluster method
            multi_cluster_data = {}
            for cluster_name in cluster_names:
                try:
                    # Convert raw results to TOTO tensor format for each cluster
                    conversion_result = prometheus_to_toto.convert_to_toto_format(
                        prometheus_data=raw_results,
                        cluster_name=cluster_name
                    )
                    
                    # Extract metric names from the raw data for this cluster
                    metric_names = self._extract_metric_names_for_cluster(raw_results, cluster_name)
                    
                    multi_cluster_data[cluster_name] = {
                        'masked_timeseries': conversion_result['masked_timeseries'],
                        'metric_names': metric_names,
                        'node_names': conversion_result['node_names'],
                        'variate_metadata': conversion_result['variate_metadata']
                    }
                    
                except Exception as e:
                    logger.warning(f"Failed to convert data for cluster {cluster_name}: {str(e)}")
                    continue
            
            if not multi_cluster_data:
                raise ValueError("No clusters could be successfully converted")
            
            # TOTO forecasting for each cluster 
            model_config = self.config['models'].get('toto', {})
            toto_adapter = TOTOAdapter(model_config)
            quantiles = self.config['models'].get('quantiles', [0.1, 0.5, 0.9])
            forecast_horizon_days = self.config['models'].get('forecast_horizon', 7)
            
            cluster_toto_forecasts = {}
            for cluster_name, cluster_info in multi_cluster_data.items():
                logger.debug(f"Generating TOTO forecast for cluster: {cluster_name}")
                
                # Calculate future steps based on input series time intervals
                masked_timeseries = cluster_info['masked_timeseries']
                time_interval_seconds = masked_timeseries.time_interval_seconds[0].item()  # Get interval from first variate
                
                # Convert forecast horizon from days to number of timesteps
                seconds_per_day = 24 * 60 * 60
                forecast_horizon_seconds = forecast_horizon_days * seconds_per_day
                future_steps = int(forecast_horizon_seconds / time_interval_seconds)
                
                logger.debug(f"Cluster {cluster_name}: time_interval={time_interval_seconds}s, "
                           f"forecast_horizon={forecast_horizon_days} days, future_steps={future_steps}")
                
                toto_forecast = toto_adapter.forecast(
                    series=masked_timeseries,
                    horizon=future_steps,
                    quantiles=quantiles,
                    variate_metadata=cluster_info['variate_metadata']
                )
                
                cluster_toto_forecasts[cluster_name] = toto_forecast
            
            # Transform TOTO output to cluster-grouped format
            format_converter = ForecastFormatConverter()
            cluster_grouped_results = {}
            
            # Convert each cluster's TOTO forecast to cluster-grouped format
            for cluster_name, toto_forecast in cluster_toto_forecasts.items():
                logger.debug(f"Converting TOTO forecast for cluster: {cluster_name}")
                
                try:
                    # Convert TOTO forecast output to cluster-grouped Prometheus format
                    cluster_forecast_entries = format_converter.convert_to_cluster_grouped_format(
                        toto_forecast_output=toto_forecast,
                        cluster_name=cluster_name
                    )
                    
                    # Store the converted forecasts for this cluster
                    cluster_grouped_results[cluster_name] = {
                        'forecasts': cluster_forecast_entries,
                        'metadata': {
                            'total_metrics': len(set(entry['metric']['__name__'] for entry in cluster_forecast_entries)),
                            'total_forecasts': len(cluster_forecast_entries),
                            'horizon_days': forecast_horizon_days,
                            'quantiles': quantiles
                        }
                    }
                    
                    logger.debug(f"Successfully converted {len(cluster_forecast_entries)} forecast entries for cluster {cluster_name}")
                    
                except Exception as e:
                    logger.error(f"Error converting TOTO forecast for cluster {cluster_name}: {str(e)}")
                    # Continue with other clusters even if one fails
                    continue
            
            logger.info(f"Successfully generated cluster-grouped forecasts for {len(cluster_grouped_results)} clusters")
            return cluster_grouped_results
            
        except Exception as e:
            logger.error(f"Error generating TOTO forecast: {str(e)}")
            raise
    
    def _extract_cluster_names_from_raw_results(self, raw_results: Dict[str, Any]) -> List[str]:
        """Extract unique cluster names from raw Prometheus results."""
        cluster_names = set()
        
        for metric_name, metric_results in raw_results.items():
            if isinstance(metric_results, list):
                for result in metric_results:
                    if isinstance(result, dict) and 'metric' in result:
                        cluster_name = result['metric'].get('clusterName')
                        if cluster_name:
                            cluster_names.add(cluster_name)
        
        return list(cluster_names)
    
    def _extract_metric_names_for_cluster(self, raw_results: Dict[str, Any], cluster_name: str) -> List[str]:
        """Extract metric names that have data for the specified cluster."""
        metric_names = []
        
        for metric_name, metric_results in raw_results.items():
            if isinstance(metric_results, list):
                # Check if this metric has data for the specified cluster
                for result in metric_results:
                    if isinstance(result, dict) and 'metric' in result:
                        if result['metric'].get('clusterName') == cluster_name:
                            metric_names.append(metric_name)
                            break  # Found data for this metric and cluster
        
        return metric_names

    def validate_forecasts(self, raw_prometheus_data: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Dict[str, float]]]:
        """Validate forecast accuracy using 70/30 train/test split with Prometheus data source.
        
        Args:
            raw_prometheus_data: Raw Prometheus query results. If None, collects fresh data.
            
        Returns:
            Dict containing validation results for all clusters
            
        Raises:
            ValueError: If no valid data is available for validation
        """
        
        try:
            # Collect raw data if not provided
            if raw_prometheus_data is None:
                logger.info("Collecting fresh Prometheus data for validation...")
                raw_prometheus_data = self.collect_raw_metrics()
            
            if not raw_prometheus_data:
                raise ValueError("No Prometheus data available for validation")
            
            # Initialize components
            validator = ForecastValidator(train_ratio=0.7)
            prometheus_adapter = PrometheusToTotoAdapter()
            
            # Get TOTO model configuration
            model_config = self.config['models'].get('toto', {})
            model_config['quantiles'] = self.config['models'].get('quantiles', [0.1, 0.5, 0.9])
            
            # Extract available clusters from raw data
            cluster_names = self._extract_cluster_names_from_raw_results(raw_prometheus_data)
            if not cluster_names:
                raise ValueError("No clusters found in Prometheus data")
            
            logger.info(f"Starting validation with TOTO model for {len(cluster_names)} clusters...")
            # Run validation and return results
            validation_results = validator.validate(
                raw_prometheus_data,
                prometheus_adapter,
                model_config,
                cluster_names
            )
            return validation_results
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            raise
    
    def run(self):
        """Run the forecasting agent continuously."""
        global exported_forecasts
        metrics_conf = self.config['metrics']
        api_port = metrics_conf.get('forecast_api_port', 8081)
        api_host = metrics_conf.get('forecast_api_host', '0.0.0.0')
        _start_forecast_server(api_host, api_port)
        
        # Check if validation is enabled
        enable_validation = self.config.get('validation', {}).get('enabled', False)
        validation_interval = self.config.get('validation', {}).get('interval_cycles', 3)
        cycle_count = 0
        
        while True:
            try:
                # Check Prometheus health before collecting metrics
                health = self.collector.health_check()
                if "unhealthy" in health["status"]:
                    logger.warning(f"Prometheus collector health check failed: {health['status']}")
                    logger.info("Retrying in 60 seconds...")
                    time.sleep(60)
                    continue
                
                logger.info("Collecting metrics...")
                
                # Collect raw Prometheus data
                raw_results = self.collect_raw_metrics()
                
                if enable_validation and cycle_count % validation_interval == 0:
                    logger.info("Running forecast validation...")
                    try:
                        validation_results = self.validate_forecasts(raw_results)
                        logger.info("TOTO validation completed successfully")
                        
                        # Store validation results for /model endpoint
                        global exported_forecasts
                        exported_forecasts['_validation_results'] = validation_results
                        
                    except Exception as e:
                        logger.error(f"TOTO validation failed: {str(e)}")
                
                model_type = self.config['models'].get('type', 'nbeats')
                
                if model_type == 'toto':
                    # Raw JSON → Tensors → TOTO forecast → Cluster-grouped format
                    logger.info("Generating TOTO forecasts ...")
                    cluster_grouped_forecasts = self.generate_forecast_TOTO(raw_results)
                    
                    # Update exported forecasts with cluster-grouped results
                    for cluster_name, forecast_entries in cluster_grouped_forecasts.items():
                        exported_forecasts[cluster_name] = forecast_entries
                        active_clusters.add(cluster_name)
                        logger.info(f"Generated forecast for cluster: {cluster_name}")
                        
                else:
                    # For NBEATS, fall back to TimeSeries-based approach
                    if cluster_timeseries is None:
                        cluster_timeseries = self.collect_metrics_timeseries()
                    
                    for cluster, ts in cluster_timeseries.items():
                        forecast = self.generate_forecast_NBEATS(ts)
                        exported_forecasts[cluster] = forecast
                        active_clusters.add(cluster)
                        logger.info(f"Generated NBEATS forecast for cluster: {cluster}")
                
                api_url = f"http://{api_host}:{api_port}/metrics/{{clustername}}"
                logger.info(f"Forecast metrics updated and available at {api_url}")
                
                recommendations = self.optimizer.optimise(exported_forecasts)
                exported_forecasts['_recommendations'] = recommendations
                
                api_url = f"http://{api_host}:{api_port}/optimize"
                logger.info(f"Optimizations recommendations are available at {api_url}")

                cycle_count += 1
                logger.info(f"Waiting {self.config['agent']['interval']}s before next collection...")
                time.sleep(self.config['agent']['interval'])
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, shutting down gracefully...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {str(e)}")
                logger.info("Retrying in 60 seconds...")
                time.sleep(60)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Forecasting Agent')
    parser.add_argument('--config', required=True, help='Path to configuration file')
    args = parser.parse_args()
    
    agent = ForecastingAgent(args.config)
    try:
        agent.run()
    except KeyboardInterrupt:
        logger.info("Forecasting agent stopped by user")
    
if __name__ == '__main__':
    main() 
