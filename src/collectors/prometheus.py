from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from prometheus_api_client import PrometheusConnect
import logging
import time
from utils.node_normalizer import create_node_mapping, normalize_metric_series

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class PrometheusCollector:
    """Prometheus metrics collector."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.timeout = config.get('timeout', 300)
        self.max_retries = config.get('max_retries', 3)
        self.chunk_threshold_days = config.get('chunk_days', 1)
        
        self.prom = PrometheusConnect(
            url=config['url'],
            headers=config.get('headers', {}),
            disable_ssl=config.get('disable_ssl', False)
        )
        
        self.last_collection: Optional[datetime] = None
        self.node_mapping: Dict[str, str] = {}
        logger.info(f"Initialized PrometheusCollector with URL: {config['url']}")

    def _execute_query(self, promql: str, start_time: datetime, end_time: datetime):
        start = start_time.astimezone(timezone.utc).replace(tzinfo=None)
        end = end_time.astimezone(timezone.utc).replace(tzinfo=None)
        
        duration = end - start
        duration_days = duration.total_seconds() / (24 * 3600)
        
        if duration_days > self.chunk_threshold_days:
            return self._execute_chunked_query(promql, start, end)
        else:
            return self._execute_single_query(promql, start, end)
    
    def _get_step_size(self) -> str:
        return self.config.get('step', '1h')
    
    def _execute_single_query(self, promql: str, start: datetime, end: datetime):
        step = self._get_step_size()
        
        for attempt in range(self.max_retries):
            try:
                result = self.prom.custom_query_range(
                    query=promql,
                    start_time=start,
                    end_time=end,
                    step=step,
                )
                logger.debug(f"Query successful, returned {len(result)} series")
                return result
                
            except Exception as e:
                logger.warning(f"Query attempt {attempt + 1} failed: {str(e)}")
                if attempt < self.max_retries - 1:
                    # Exponential backoff: 2^attempt seconds
                    sleep_time = 2 ** attempt
                    logger.info(f"Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"All {self.max_retries} query attempts failed")
                    raise
    
    def _execute_chunked_query(self, promql: str, start: datetime, end: datetime):
        chunk_size = timedelta(days=self.chunk_threshold_days)
        all_results = []
        current_start = start
        
        chunk_count = 0
        while current_start < end:
            chunk_count += 1
            current_end = min(current_start + chunk_size, end)
            
            try:
                chunk_result = self._execute_single_query(promql, current_start, current_end)
                if chunk_result:
                    all_results.extend(chunk_result)
                
            except Exception as e:
                logger.error(f"Chunk {chunk_count} failed: {str(e)}")
                continue
            
            current_start = current_end
        
        logger.debug(f"Chunked query completed: {chunk_count} chunks, {len(all_results)} total series")
        return all_results

    def collect_metrics(self, start_time: datetime, end_time: datetime, promq: Dict[str, str]) -> Dict[str, list]:
        """Collect multiple Prometheus metrics and return the Prometheus query results."""
        if not self.config.get('node_normalization', {}).get('enabled', True):
            logger.info("Node normalization is disabled, collecting metrics without normalization")
            return self._collect_raw_metrics(start_time, end_time, promq)
        
        if not self.node_mapping:
            self.load_node_mappings(start_time, end_time)
        
        raw_results = self._collect_raw_metrics(start_time, end_time, promq)
        
        # Apply node normalization to each metric
        normalized_results = {}
        for metric_key, metric_data in raw_results.items():
            if metric_data:
                normalized_data = normalize_metric_series(metric_data, self.node_mapping, metric_key)
                normalized_results[metric_key] = normalized_data
            else:
                normalized_results[metric_key] = metric_data
        
        logger.info(f"Collected and normalized {len(normalized_results)} metrics")
        return normalized_results
    
    def _collect_raw_metrics(self, start_time: datetime, end_time: datetime, promq: Dict[str, str]) -> Dict[str, list]:
        """Collect raw metrics without normalization."""
        results: Dict[str, list] = {}
        for metric_key, promql in promq.items():
            try:
                raw_result = self._execute_query(promql, start_time, end_time)
                results[metric_key] = raw_result
            except Exception as e:
                logger.error(f"Error collecting metric '{metric_key}': {e}")
                continue

        if not results or all(len(v) == 0 for v in results.values()):
            raise ValueError("No metrics data collected from Prometheus.")

        # Record timestamp of successful collection for health_check()
        self.last_collection = datetime.now()
        return results

    def load_node_mappings(self, start_time: datetime, end_time: datetime) -> None:
        """Load node name mappings from kube_node_info metric."""
        if not self.config.get('node_normalization', {}).get('enabled', True):
            logger.info("Node normalization is disabled")
            return
        
        try:
            kube_node_info_query = self.config.get('node_normalization', {}).get('kube_node_info_query', 'kube_node_info')
            kube_node_info_data = self._execute_query(kube_node_info_query, start_time, end_time)
            
            if kube_node_info_data:
                self.node_mapping = create_node_mapping(kube_node_info_data)
                logger.info("Successfully loaded node mappings")
                
                if self.config.get('node_normalization', {}).get('log_mapping_stats', False):
                    logger.info(f"Node mapping stats: {len(self.node_mapping)} mappings loaded")
            else:
                logger.warning("No kube_node_info data found, node normalization will be disabled")
                
        except Exception as e:
            logger.error(f"Failed to load node mappings: {str(e)}")
            logger.warning("Node normalization will be disabled")

    def get_available_metrics(self) -> List[str]:
        """Get list of available Prometheus metrics."""
        try:
            return self.prom.all_metrics()
        except Exception as e:
            logger.error(f"Error getting available metrics: {str(e)}")
            return []

    def health_check(self) -> Dict[str, Any]:
        """Check Prometheus collector health."""
        try:
            self.prom.check_prometheus_connection()
            status = "healthy"
        except Exception as e:
            status = f"unhealthy: {str(e)}"

        return {
            "status": status,
            "last_collection": self.last_collection,
            "prometheus_url": self.config['url']
        }
