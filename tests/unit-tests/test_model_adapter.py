import os
import sys
import types
import torch
import numpy as np
import pytest

# ensure src is importable
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from toto.data.util.dataset import MaskedTimeseries  # type: ignore
except Exception:
    class MaskedTimeseries:  # type: ignore
        def __init__(self, series, padding_mask, id_mask, timestamp_seconds, time_interval_seconds):
            self.series = series
            self.padding_mask = padding_mask
            self.id_mask = id_mask
            self.timestamp_seconds = timestamp_seconds
            self.time_interval_seconds = time_interval_seconds

from adapters.forecasting.toto_adapter import TOTOAdapter


def build_simple_mts(n_variates: int = 2, n_steps: int = 10) -> MaskedTimeseries:
    series = torch.stack([
        torch.linspace(50, 59, n_steps),   # percentage-like metric
        torch.linspace(100, 109, n_steps), # memory total GB metric
    ], dim=0).to(torch.float32)

    padding_mask = torch.ones((n_variates, n_steps), dtype=torch.bool)
    id_mask = torch.zeros((n_variates, n_steps), dtype=torch.float32)
    timestamp_seconds = torch.arange(1_720_000_000, 1_720_000_000 + n_steps, dtype=torch.int64)
    timestamp_seconds = timestamp_seconds.unsqueeze(0).expand(n_variates, n_steps)
    time_interval_seconds = torch.full((n_variates,), 3600, dtype=torch.int64)

    return MaskedTimeseries(
        series=series,
        padding_mask=padding_mask,
        id_mask=id_mask,
        timestamp_seconds=timestamp_seconds,
        time_interval_seconds=time_interval_seconds,
    )


class DummyForecast:
    def __init__(self, samples: torch.Tensor):
        self.samples = samples


class DummyForecaster:
    def __init__(self):
        pass

    def forecast(
        self,
        inputs,
        *,
        prediction_length: int,
        num_samples: int,
        timestamp_seconds=None,
        time_interval_seconds=None,
        input_padding_mask=None,
        id_mask=None,
        samples_per_batch=None,
        use_kv_cache: bool = False,
    ):
        series = inputs.series if hasattr(inputs, 'series') else inputs
        last_vals = series[:, -1]
        base = last_vals.unsqueeze(0).unsqueeze(-1).repeat(num_samples, 1, prediction_length).contiguous()
        return DummyForecast(base)


def test_toto_adapter_forecast_quantiles_and_structure():
    mts = build_simple_mts()
    horizon = 4

    variate_metadata = [
        {
            'metric_name': 'cpu_pct_per_cluster',
            'node_name': 'cluster-aggregate',
            'variate_id': 'cpu_pct_per_cluster_cluster-aggregate'
        },
        {
            'metric_name': 'mem_total_gb_per_cluster',
            'node_name': 'cluster-aggregate',
            'variate_id': 'mem_total_gb_per_cluster_cluster-aggregate'
        }
    ]

    last_vals = mts.series[:, -1]

    def make_samples(pred_len: int, num_samples: int) -> torch.Tensor:
        # shape: (num_samples, n_variates, horizon)
        base = last_vals.unsqueeze(0).unsqueeze(-1).expand(num_samples, mts.series.shape[0], pred_len)
        noise = torch.zeros_like(base)
        return base + noise

    adapter = TOTOAdapter(config={})

    def fake_ensure_loaded():
        adapter._model_loaded = True
        adapter._forecaster = DummyForecaster()

    adapter._ensure_model_loaded = fake_ensure_loaded  # type: ignore

    result = adapter.forecast(
        series=mts,
        horizon=horizon,
        quantiles=[0.5],
        variate_metadata=variate_metadata,
    )

    assert 'series' in result and 'timestamps' in result and 'horizon' in result
    assert result['horizon'] == horizon
    assert len(result['timestamps']) == horizon

    series_out = result['series']
    assert set(series_out.keys()) == {m['variate_id'] for m in variate_metadata}

    cpu_q = series_out['cpu_pct_per_cluster_cluster-aggregate']['quantiles']['q0.50']
    mem_q = series_out['mem_total_gb_per_cluster_cluster-aggregate']['quantiles']['q0.50']

    assert np.allclose(cpu_q, np.full(horizon, float(last_vals[0].item())), atol=1e-5)
    assert np.allclose(mem_q, np.full(horizon, float(last_vals[1].item())), atol=1e-5)


def _run_as_script():
    try:
        test_toto_adapter_forecast_quantiles_and_structure()
        print("✅ Model adapter test passed")
    except Exception as e:
        print(f"\n❌ UNIT TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        import sys as _sys
        _sys.exit(1)


if __name__ == "__main__":
    _run_as_script()