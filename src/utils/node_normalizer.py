from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

def create_node_mapping(kube_node_info_data: List[Dict[str, Any]]) -> Dict[str, str]:
    """Create node mapping from kube_node_info metric data.

    Args:
        kube_node_info_data: List of kube_node_info metric series

    Returns:
        Dictionary mapping node identifiers to normalized node names
    """
    node_mapping = {}

    for series in kube_node_info_data:
        metric = series.get('metric', {})

        # Extract node information
        node_name = metric.get('node')
        internal_ip = metric.get('internal_ip')
        instance = metric.get('instance')
        provider_id = metric.get('provider_id')
        if node_name:
            # Map internal IP to node name
            if internal_ip:
                node_mapping[internal_ip] = node_name
                # Also map with port if present
                if ':' in internal_ip:
                    base_ip = internal_ip.split(':')[0]
                    node_mapping[base_ip] = node_name

            # Map instance to node name
            if instance:
                node_mapping[instance] = node_name
                # Also map without port
                if ':' in instance:
                    base_instance = instance.split(':')[0]
                    node_mapping[base_instance] = node_name

            # Map provider ID to node name
            if provider_id:
                node_mapping[provider_id] = node_name

    logger.info(f"Created {len(node_mapping)} node mappings")
    logger.debug(f"Node mappings: {node_mapping}")
    return node_mapping

def normalize_node_name(node_identifier: str, node_mapping: Dict[str, str], metric_name: str = "") -> str:
    """Normalize a node identifier to a consistent node name.

    Args:
        node_identifier: The node identifier from the metric (could be IP, instance, etc.)
        node_mapping: Dictionary of node mappings
        metric_name: Optional metric name for logging context

    Returns:
        Normalized node name
    """
    if not node_mapping:
        logger.debug(f"No node mapping available, returning original identifier: {node_identifier}")
        return node_identifier

    # Try exact match first
    if node_identifier in node_mapping:
        normalized = node_mapping[node_identifier]
        logger.debug(f"Normalized {node_identifier} -> {normalized} for metric {metric_name}")
        return normalized

    # Try without port if present
    if ':' in node_identifier:
        base_identifier = node_identifier.split(':')[0]
        if base_identifier in node_mapping:
            normalized = node_mapping[base_identifier]
            logger.debug(f"Normalized {node_identifier} -> {normalized} for metric {metric_name}")
            return normalized

    # If no mapping found, log and return original
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

    # Determine if this is a cluster-level metric
    is_cluster_level = metric_name.endswith('_per_cluster')
    
    normalized_series = []

    for series in series_data:
        metric = series.get('metric', {})
        normalized_metric = metric.copy()

        if is_cluster_level:
            # For cluster-level metrics, set node='cluster-aggregate' and remove other node labels
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
                # Normalize the node value
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
