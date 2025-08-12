"""
Pytest configuration for forecasting agent tests.
"""

import sys
import os
import pytest

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Configure logging for tests
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

@pytest.fixture(scope="session")
def test_config():
    """Provide test configuration."""
    return {
        'collector': {
            'prometheus_url': 'http://localhost:9090',
            'lookback_days': 1
        },
        'models': {
            'forecast_horizon': 7,
        },
        'optimizer': {
            'idle_threshold': 0.5,
            'min_savings': 5.0,
            'lookback_days': 7,
            'min_confidence': 0.7
        },
        'metrics': {
            'port': 8001,
            'host': '0.0.0.0'
        },
        'agent': {
            'interval': 3600
        }
    }