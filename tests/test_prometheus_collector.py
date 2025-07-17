import pytest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from src.collectors.prometheus import PrometheusCollector


class TestPrometheusCollectorBasic:
    
    @pytest.fixture
    def mock_prometheus_data(self):
        """Mock Prometheus query result data."""
        return [
            {
                'metric': {'__name__': 'cpu_usage', 'instance': 'node1'},
                'values': [[1620000000 + i*3600, str(0.5 + i*0.01)] for i in range(120)]  # 5 days of hourly data
            },
            {
                'metric': {'__name__': 'memory_usage', 'instance': 'node1'}, 
                'values': [[1620000000 + i*3600, str(1000 + i*10)] for i in range(120)]
            }
        ]
    
    @pytest.fixture
    def time_range_5_days(self):
        """Create 5-day time range for testing."""
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=5)
        return start_time, end_time
    
    def test_should_collect_metrics_for_5_days_with_1h_step(self, mock_prometheus_data, time_range_5_days):
        """Test collecting metrics for 5 days with 1h step size."""
        config = {
            'url': 'http://localhost:9090',
            'step': '1h',
            'chunk_days': 0.25  # 6 hours
        }
        collector = PrometheusCollector(config)
        start_time, end_time = time_range_5_days
        
        promq = {
            'cpu_usage': 'rate(cpu_seconds_total[5m])',
            'memory_usage': 'node_memory_MemAvailable_bytes'
        }
        
        with patch.object(collector.prom, 'custom_query_range') as mock_query:
            mock_query.return_value = mock_prometheus_data
            
            result = collector.collect_metrics_timeseries(start_time, end_time, promq)
            
            # Should return data for both metrics
            assert 'cpu_usage' in result
            assert 'memory_usage' in result
            # With 5-day range and 0.25-day chunks: 20 chunks × 2 series each = 40 total series
            assert len(result['cpu_usage']) == 40  # Chunked results
            assert len(result['memory_usage']) == 40
            
            # Should use 1h step size
            mock_query.assert_called()
            call_args = mock_query.call_args_list[0][1]
            assert call_args['step'] == '1h'
    
    def test_should_collect_metrics_for_5_days_with_30m_step(self, mock_prometheus_data, time_range_5_days):
        """Test collecting metrics for 5 days with 30m step size."""
        config = {
            'url': 'http://localhost:9090',
            'step': '30m',
            'chunk_days': 0.25  # 6 hours
        }
        collector = PrometheusCollector(config)
        start_time, end_time = time_range_5_days
        
        promq = {'test_metric': 'up'}
        
        with patch.object(collector.prom, 'custom_query_range') as mock_query:
            mock_query.return_value = mock_prometheus_data
            
            result = collector.collect_metrics_timeseries(start_time, end_time, promq)
            
            # Should return data
            assert 'test_metric' in result
            assert len(result['test_metric']) > 0
            
            # Should use 30m step size
            call_args = mock_query.call_args_list[0][1]
            assert call_args['step'] == '30m'
    
    def test_should_collect_metrics_for_5_days_with_1m_step(self, mock_prometheus_data, time_range_5_days):
        """Test collecting metrics for 5 days with 1m step size."""
        config = {
            'url': 'http://localhost:9090',
            'step': '1m',
            'chunk_days': 0.25  # 6 hours
        }
        collector = PrometheusCollector(config)
        start_time, end_time = time_range_5_days
        
        promq = {'high_res_metric': 'node_cpu_seconds_total'}
        
        with patch.object(collector.prom, 'custom_query_range') as mock_query:
            mock_query.return_value = mock_prometheus_data
            
            result = collector.collect_metrics_timeseries(start_time, end_time, promq)
            
            # Should return data
            assert 'high_res_metric' in result
            assert len(result['high_res_metric']) > 0
            
            # Should use 1m step size  
            call_args = mock_query.call_args_list[0][1]
            assert call_args['step'] == '1m'
    
    def test_should_use_chunking_for_5_day_range(self, mock_prometheus_data, time_range_5_days):
        """Test that 5-day range uses chunked queries"""
        config = {
            'url': 'http://localhost:9090', 
            'step': '1h',
            'chunk_days': 0.25  # 6 hours
        }
        collector = PrometheusCollector(config)
        start_time, end_time = time_range_5_days
        
        promq = {'chunked_metric': 'up'}
        
        with patch.object(collector.prom, 'custom_query_range') as mock_query:
            mock_query.return_value = mock_prometheus_data
            
            result = collector.collect_metrics_timeseries(start_time, end_time, promq)
            
            # Should return data
            assert 'chunked_metric' in result
            assert len(result['chunked_metric']) > 0
            
            # Should make multiple calls due to chunking (5 days > 0.25 day threshold)
            assert mock_query.call_count >= 15  # At least 15 chunks (expecting ~20)
    
    def test_should_return_empty_when_no_data_available(self, time_range_5_days):
        """Test behavior when Prometheus returns no data."""
        config = {
            'url': 'http://localhost:9090',
            'step': '1h'
        }
        collector = PrometheusCollector(config)
        start_time, end_time = time_range_5_days
        
        promq = {'no_data_metric': 'nonexistent_metric'}
        
        with patch.object(collector.prom, 'custom_query_range') as mock_query:
            mock_query.return_value = []  # No data
            
            with pytest.raises(ValueError, match="No metrics data collected"):
                collector.collect_metrics_timeseries(start_time, end_time, promq)
