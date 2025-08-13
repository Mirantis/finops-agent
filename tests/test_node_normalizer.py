import pytest
from src.utils.node_normalizer import create_node_mapping, normalize_node_name, normalize_metric_series

class TestNodeNormalizer:

    def setup_method(self):
        """Set up test fixtures."""
        # Sample kube_node_info data
        self.sample_kube_node_info = [
            {
                'metric': {
                    '__name__': 'kube_node_info',
                    'cluster': 'aws-ramesses-regional',
                    'node': 'aws-ramesses-regional-cp-0',
                    'internal_ip': '10.0.111.163',
                    'instance': '10.244.110.9:8080',
                    'provider_id': 'aws:///ap-south-1a/i-003c1d4f4e1c19d3b'
                }
            },
            {
                'metric': {
                    '__name__': 'kube_node_info',
                    'cluster': 'aws-ramesses-regional',
                    'node': 'aws-ramesses-regional-md-1',
                    'internal_ip': '10.0.111.164',
                    'instance': '10.244.110.10:8080',
                    'provider_id': 'aws:///ap-south-1a/i-003c1d4f4e1c19d3c'
                }
            },
            {
                'metric': {
                    '__name__': 'kube_node_info',
                    'cluster': 'aws-ramesses-regional',
                    'node': 'aws-ramesses-regional-md-2',
                    'internal_ip': '10.0.111.165',
                    'instance': '10.244.110.11:8080',
                    'provider_id': 'aws:///ap-south-1a/i-003c1d4f4e1c19d3d'
                }
            }
        ]
        self.node_mapping = create_node_mapping(self.sample_kube_node_info)

    def test_create_node_mapping(self):
        """Test creating node mappings from kube_node_info data."""
        node_mapping = create_node_mapping(self.sample_kube_node_info)

        # Should have mappings for all three nodes
        # Each node creates 4 mappings: internal_ip, internal_ip (no port), instance, instance (no port), provider_id
        assert len(node_mapping) == 12  # 3 nodes × 4 mappings each

        # Check mappings for first node (cp-0)
        assert node_mapping['10.0.111.163'] == 'aws-ramesses-regional-cp-0'
        assert node_mapping['10.244.110.9:8080'] == 'aws-ramesses-regional-cp-0'
        assert node_mapping['aws:///ap-south-1a/i-003c1d4f4e1c19d3b'] == 'aws-ramesses-regional-cp-0'

        # Check mappings for second node (md-1)
        assert node_mapping['10.0.111.164'] == 'aws-ramesses-regional-md-1'
        assert node_mapping['10.244.110.10:8080'] == 'aws-ramesses-regional-md-1'
        assert node_mapping['aws:///ap-south-1a/i-003c1d4f4e1c19d3c'] == 'aws-ramesses-regional-md-1'

        # Check mappings for third node (md-2)
        assert node_mapping['10.0.111.165'] == 'aws-ramesses-regional-md-2'
        assert node_mapping['10.244.110.11:8080'] == 'aws-ramesses-regional-md-2'
        assert node_mapping['aws:///ap-south-1a/i-003c1d4f4e1c19d3d'] == 'aws-ramesses-regional-md-2'
    
    def test_normalize_node_name_exact_match(self):
        """Test normalizing node names with exact matches."""
        node_mapping = create_node_mapping(self.sample_kube_node_info)
        
        # Test exact matches
        assert normalize_node_name('10.0.111.163', node_mapping) == 'aws-ramesses-regional-cp-0'
        assert normalize_node_name('10.244.110.9:8080', node_mapping) == 'aws-ramesses-regional-cp-0'
        assert normalize_node_name('aws:///ap-south-1a/i-003c1d4f4e1c19d3b', node_mapping) == 'aws-ramesses-regional-cp-0'
    
    def test_normalize_node_name_with_port(self):
        """Test normalizing node names with port numbers."""
        node_mapping = create_node_mapping(self.sample_kube_node_info)
        
        # Test with port
        assert normalize_node_name('10.0.111.163:9100', node_mapping) == 'aws-ramesses-regional-cp-0'
        assert normalize_node_name('10.244.110.9:8080', node_mapping) == 'aws-ramesses-regional-cp-0'
    
    def test_normalize_node_name_no_mapping(self):
        """Test normalizing node names with no mapping found."""
        node_mapping = create_node_mapping(self.sample_kube_node_info)
        
        # Test unknown node identifier
        unknown_node = 'unknown-node-123'
        result = normalize_node_name(unknown_node, node_mapping)
        assert result == unknown_node  # Should return original if no mapping
    
    def test_normalize_metric_series(self):
        """Test normalizing node names in metric series."""
        node_mapping = create_node_mapping(self.sample_kube_node_info)
        
        # Sample metric series with different node labels across all three nodes
        sample_series = [
            {
                'metric': {
                    '__name__': 'cpu_usage',
                    'node': '10.0.111.163:9100',
                    'cluster': 'aws-ramesses-regional'
                }
            },
            {
                'metric': {
                    '__name__': 'memory_usage',
                    'instance': '10.244.110.9:8080',
                    'cluster': 'aws-ramesses-regional'
                }
            },
            {
                'metric': {
                    '__name__': 'disk_usage',
                    'node': '10.0.111.164',
                    'cluster': 'aws-ramesses-regional'
                }
            },
            {
                'metric': {
                    '__name__': 'network_usage',
                    'instance': '10.244.110.11:8080',
                    'cluster': 'aws-ramesses-regional'
                }
            }
        ]
        
        normalized = normalize_metric_series(sample_series, node_mapping, 'test_metric')
        
        assert len(normalized) == 4
        # All metrics should now have 'node' label (not 'instance')
        # First should map to cp-0
        assert normalized[0]['metric']['node'] == 'aws-ramesses-regional-cp-0'
        # Second should map to cp-0 (instance converted to node)
        assert normalized[1]['metric']['node'] == 'aws-ramesses-regional-cp-0'
        # Third should map to md-1
        assert normalized[2]['metric']['node'] == 'aws-ramesses-regional-md-1'
        # Fourth should map to md-2 (instance converted to node)
        assert normalized[3]['metric']['node'] == 'aws-ramesses-regional-md-2'
        
        # Verify that all metrics now use 'node' label consistently
        for metric in normalized:
            assert 'node' in metric['metric']
            assert 'instance' not in metric['metric']
            assert 'nodename' not in metric['metric']
    
    def test_normalize_without_mapping(self):
        """Test normalizing when no mapping is available."""
        # Test with empty mapping
        result = normalize_node_name('10.0.111.163', {})
        assert result == '10.0.111.163'  # Should return original
        
        # Test with None mapping
        result = normalize_node_name('10.0.111.163', None)
        assert result == '10.0.111.163'  # Should return original
    
    def test_complete_label_standardization(self):
        """Test that normalize_metric_series completely standardizes labels for downstream use."""
        # Test cluster-level metric standardization
        cluster_series = [
            {
                'metric': {
                    '__name__': 'cost_usd_per_cluster',
                    'cluster': 'aws-ramesses-regional',
                    'instance': '10.244.110.9:8080',  # Should be removed
                    'node': 'some-old-node'  # Should be replaced
                }
            }
        ]
        
        normalized_cluster = normalize_metric_series(cluster_series, self.node_mapping, 'cost_usd_per_cluster')
        
        # Should have only 'node' label with value 'cluster-aggregate'
        metric = normalized_cluster[0]['metric']
        assert metric['node'] == 'cluster-aggregate'
        assert 'instance' not in metric
        assert 'nodename' not in metric
        
        # Test node-level metric standardization
        node_series = [
            {
                'metric': {
                    '__name__': 'cpu_pct_per_node',
                    'cluster': 'aws-ramesses-regional',
                    'instance': '10.244.110.9:8080'  # Should become 'node' and be normalized
                }
            },
            {
                'metric': {
                    '__name__': 'mem_pct_per_node',
                    'cluster': 'aws-ramesses-regional',
                    'nodename': 'aws-ramesses-regional-cp-0'  # Should become 'node'
                }
            }
        ]
        
        normalized_node = normalize_metric_series(node_series, self.node_mapping, 'cpu_pct_per_node')
        
        # First metric: instance should become node and be normalized
        first_metric = normalized_node[0]['metric']
        assert first_metric['node'] == 'aws-ramesses-regional-cp-0'  # Normalized from IP
        assert 'instance' not in first_metric
        
        # Second metric: nodename should become node
        second_metric = normalized_node[1]['metric']
        assert second_metric['node'] == 'aws-ramesses-regional-cp-0'
        assert 'nodename' not in second_metric
        
        # Verify that downstream logic only needs to check 'node' label
        for metric in normalized_node:
            assert 'node' in metric['metric']
            assert 'instance' not in metric['metric']
            assert 'nodename' not in metric['metric']
    
    def test_comprehensive_node_mapping_scenarios(self):
        """Test comprehensive node mapping scenarios across all three nodes."""
        node_mapping = create_node_mapping(self.sample_kube_node_info)
        
        # Test all mapping scenarios for each node
        # Node 1: aws-ramesses-regional-cp-0
        assert normalize_node_name('10.0.111.163', node_mapping) == 'aws-ramesses-regional-cp-0'
        assert normalize_node_name('10.0.111.163:9100', node_mapping) == 'aws-ramesses-regional-cp-0'
        assert normalize_node_name('10.244.110.9:8080', node_mapping) == 'aws-ramesses-regional-cp-0'
        assert normalize_node_name('10.244.110.9', node_mapping) == 'aws-ramesses-regional-cp-0'
        assert normalize_node_name('aws:///ap-south-1a/i-003c1d4f4e1c19d3b', node_mapping) == 'aws-ramesses-regional-cp-0'
        
        # Node 2: aws-ramesses-regional-md-1
        assert normalize_node_name('10.0.111.164', node_mapping) == 'aws-ramesses-regional-md-1'
        assert normalize_node_name('10.0.111.164:9100', node_mapping) == 'aws-ramesses-regional-md-1'
        assert normalize_node_name('10.244.110.10:8080', node_mapping) == 'aws-ramesses-regional-md-1'
        assert normalize_node_name('10.244.110.10', node_mapping) == 'aws-ramesses-regional-md-1'
        assert normalize_node_name('aws:///ap-south-1a/i-003c1d4f4e1c19d3c', node_mapping) == 'aws-ramesses-regional-md-1'
        
        # Node 3: aws-ramesses-regional-md-2
        assert normalize_node_name('10.0.111.165', node_mapping) == 'aws-ramesses-regional-md-2'
        assert normalize_node_name('10.0.111.165:9100', node_mapping) == 'aws-ramesses-regional-md-2'
        assert normalize_node_name('10.244.110.11:8080', node_mapping) == 'aws-ramesses-regional-md-2'
        assert normalize_node_name('10.244.110.11', node_mapping) == 'aws-ramesses-regional-md-2'
        assert normalize_node_name('aws:///ap-south-1a/i-003c1d4f4e1c19d3d', node_mapping) == 'aws-ramesses-regional-md-2'