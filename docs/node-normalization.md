# Node Name Normalization

## Overview

Different Prometheus metrics use different labels for node identification:

- Some use `node` with proper names: `aws-ramesses-regional-cp-0`
- Some use `instance` with IP addresses: `10.0.111.163:9100`
- Some use `nodename` with different formats
- This inconsistency causes issues in node-level forecasting and aggregation

## Solution

The node normalization system:

1. **Queries `kube_node_info` metric** to get node mapping data
2. **Creates a mapping table** between IPs/instances and proper node names
3. **Applies normalization** to all collected metrics during collection
4. **Ensures consistent node naming** throughout the forecasting pipeline

## Configuration

Add this section to your `config.yaml`:

```yaml
# Node normalization configuration
node_normalization:
  enabled: True                                    # Enable/disable the feature
  kube_node_info_query: "kube_node_info"          # Query to get node mappings
  fallback_to_original: True                       # Return original name if no mapping found
  log_mapping_stats: True                          # Log mapping statistics for debugging
```

## Example

### Before Normalization:

```json
{
  "metric": {
    "__name__": "cpu_usage",
    "node": "10.0.111.163:9100",
    "cluster": "aws-ramesses-regional"
  }
}
```

### After Normalization:

```json
{
  "metric": {
    "__name__": "cpu_usage", 
    "node": "aws-ramesses-regional-cp-0",
    "cluster": "aws-ramesses-regional"
  }
}
```

## Troubleshooting

### Check if normalization is working

```bash
# Look for these log messages:
"Successfully loaded node mappings"
"Node mapping stats: {...}"
"Collected and normalized X metrics"
```

### If normalization is disabled

```bash
# Look for:
"Node normalization is disabled"
"Failed to load node mappings"
```

### Verify kube_node_info data

```bash
# Query Prometheus directly:
curl "http://your-prometheus:9090/api/v1/query?query=kube_node_info"
```

## Performance Impact

- **Minimal overhead**: Node mapping is loaded once per collection cycle
- **Efficient processing**: Uses in-memory mapping table
- **Configurable**: Can be disabled if performance is critical
