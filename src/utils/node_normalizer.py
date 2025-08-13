from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

def create_node_mapping(kube_node_info_data: List[Dict[str, Any]]) -> Dict[str, str]:
    """Create node mapping from kube_node_info metric data."""
    node_mapping = {}

    for series in kube_node_info_data:
        metric = series.get('metric', {})

        node_name = metric.get('node')
        internal_ip = metric.get('internal_ip')
        instance = metric.get('instance')
        provider_id = metric.get('provider_id')
        
        if node_name:
            if internal_ip:
                node_mapping[internal_ip] = node_name
                # Also map with port if present
                if ':' in internal_ip:
                    base_ip = internal_ip.split(':')[0]
                    node_mapping[base_ip] = node_name

            if instance:
                node_mapping[instance] = node_name
                # Also map without port
                if ':' in instance:
                    base_instance = instance.split(':')[0]
                    node_mapping[base_instance] = node_name

            if provider_id:
                node_mapping[provider_id] = node_name

    logger.info(f"Created {len(node_mapping)} node mappings")
    return node_mapping

def normalize_node_name(node_identifier: str, node_mapping: Dict[str, str], metric_name: str = "") -> str:
    """Normalize a node identifier to a consistent node name."""
    if not node_mapping:
        return node_identifier

    if node_identifier in node_mapping:
        return node_mapping[node_identifier]

    if ':' in node_identifier:
        base_identifier = node_identifier.split(':')[0]
        if base_identifier in node_mapping:
            return node_mapping[base_identifier]

    logger.debug(f"No mapping found for node identifier: {node_identifier} in metric {metric_name}")
    return node_identifier

def normalize_metric_series(series_data: List[Dict[str, Any]], node_mapping: Dict[str, str], metric_name: str = "") -> List[Dict[str, Any]]:
    """Normalize and standardize node names in a list of metric series.
    
    This function ensures that:
    1. All node identifiers are normalized to consistent node names
    2. All metrics use a single 'node' label (not 'instance', 'nodename', etc.)
    3. Cluster-level metrics get node='cluster-aggregate'
    4. Downstream logic doesn't need to check different node label names

    Args:
        series_data: List of metric series data
        node_mapping: Dictionary of node mappings
        metric_name: Name of the metric for logging context

    Returns:
        List of metric series with completely standardized node labels
    """
    if not node_mapping:
        logger.debug(f"No node mapping available for metric {metric_name}, returning original data")
        return series_data

    is_cluster_level = metric_name.endswith('_per_cluster')
    normalized_series = []

    for series in series_data:
        metric = series.get('metric', {})
        normalized_metric = metric.copy()

        if is_cluster_level:
            for label in ['node', 'nodename', 'instance']:
                if label in normalized_metric:
                    del normalized_metric[label]
            normalized_metric['node'] = 'cluster-aggregate'
        else:
            # For node-level metrics, find any node identifier and normalize it
            node_value = None
            
            # Check all possible node label names and get the first one found
            for label in ['node', 'nodename', 'instance']:
                if label in normalized_metric:
                    node_value = normalized_metric[label]
                    # Remove the original label
                    del normalized_metric[label]
                    break
            
            if node_value:
                normalized_node = normalize_node_name(node_value, node_mapping, metric_name)
                normalized_metric['node'] = normalized_node
            else:
                # No node identifier found, set to unknown
                normalized_metric['node'] = 'unknown'

        # Create new series with standardized metric
        normalized_series.append({
            **series,
            'metric': normalized_metric
        })

    logger.debug(f"Normalized and standardized {len(normalized_series)} series for metric {metric_name} (cluster-level: {is_cluster_level})")
    return normalized_series
