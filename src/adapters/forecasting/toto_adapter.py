import logging
from typing import List, Dict, Optional, Any
import time
import os

import numpy as np
import torch
from functools import lru_cache
from toto.data.util.dataset import MaskedTimeseries
from toto.inference.forecaster import TotoForecaster
from toto.model.toto import Toto

@lru_cache(maxsize=None)
def _get_cached_toto_model(checkpoint: str, device: str, compile_model: bool):
    normalized_device = str(torch.device(device))
    model = Toto.from_pretrained(checkpoint).to(normalized_device)
    if compile_model:
        model.compile()
    return model

class TOTOAdapter:
    """Adapter for Datadog's TOTO zero-shot forecasting model."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self._model = None
        self._forecaster = None
        self._model_loaded = False

    def _ensure_model_loaded(self):
        """Ensure TOTO model is loaded, downloading if necessary."""
        if self._model_loaded:
            return

        try:
            checkpoint = self.config.get("checkpoint", "Datadog/Toto-Open-Base-1.0")
            device = self.config.get("device", "cpu")
            compile_model = self.config.get("compile", True)

            self.logger.info(f"Loading TOTO model (cached): {checkpoint} on {device}")
            self._model = _get_cached_toto_model(checkpoint, device, compile_model)

            self._forecaster = TotoForecaster(self._model.model)
            self._model_loaded = True
            self.logger.info("TOTO model loaded successfully")

        except Exception as e:
            self.logger.error(f"Failed to load TOTO model: {str(e)}")
            self._model = None
            self._forecaster = None
            self._model_loaded = False
            raise

    def forecast(
        self,
        series: MaskedTimeseries,
        horizon: int,
        quantiles: Optional[List[float]] = None,
        variate_metadata: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Generate a horizon-step forecast for the given MaskedTimeseries.

        Parameters
        ----------
        series : MaskedTimeseries
            Historical multivariate tensor input data.
        horizon : int
            Number of future steps to predict.
        quantiles : list[float], optional
            Quantiles to emit; defaults to [0.1, 0.5, 0.9].
        variate_metadata : list[dict], optional
            Metadata for each tensor variate. Each dict should contain:
            - 'metric_name': Name of the metric (e.g., 'cost_usd_per_node')
            - 'node_name': Name of the node (e.g., 'test-cluster-cp-0')
            - 'variate_id': Unique identifier for this variate
            If not provided, generic metadata will be generated.

        Returns
        -------
        Dict containing:
            - 'samples': Raw forecast samples tensor
            - 'series': Series data organized by variate_id, each containing quantiles and metadata
            - 'timestamps': Future timestamps
            - 'variate_metadata': Metadata for each variate
            - 'horizon': Forecast horizon
            - 'time_interval_seconds': Time interval in seconds
        """
        # Ensure model is loaded before forecasting
        self._ensure_model_loaded()

        quantiles = quantiles or [0.1, 0.5, 0.9]

        # Set default variate metadata if not provided
        if variate_metadata is None:
            variate_metadata = [
                {
                    'metric_name': f'metric_{i}',
                    'node_name': f'node_{i}',
                    'variate_id': f'variate_{i}'
                }
                for i in range(series.series.shape[0])
            ]

        # Percentage metrics: scale 0-100 -> 0-1 for model stability, rescale later.
        # Cost metrics: apply log1p transform before model and expm1 after.
        # Build scale metadata lists to invert transformation later.
        n_variates = series.series.shape[0]
        transformed_series = series.series.clone().float()
        transform_types = [None] * n_variates  # 'pct' | 'log' | None
        for idx, meta in enumerate(variate_metadata):
            mname = meta.get('metric_name', '')
            if '_pct_' in mname:
                # scale percentages to fraction
                transformed_series[idx] = transformed_series[idx] / 100.0
                transform_types[idx] = 'pct'
            elif 'cost_usd_' in mname:
                transformed_series[idx] = torch.log1p(torch.clamp_min(transformed_series[idx], 0.0))
                transform_types[idx] = 'log'
        
        series_scaled = MaskedTimeseries(
            transformed_series,
            series.padding_mask,
            series.id_mask,
            series.timestamp_seconds,
            series.time_interval_seconds,
        )

        forecast_result = self._run_toto_inference(series_scaled, horizon)

        # Generate future timestamps
        last_timestamp = series.timestamp_seconds[0, -1].item()
        time_interval = series.time_interval_seconds[0].item()
        future_timestamps = [
            int((last_timestamp + (i + 1) * time_interval) * 1000)  # Convert to milliseconds
            for i in range(horizon)
        ]

        # Calculate quantiles for each variate (node-metric combination)
        samples = forecast_result.samples  # Shape: (num_samples, n_variates, horizon)
        # Invert transforms per variate
        for idx, ttype in enumerate(transform_types):
            if ttype == 'pct':
                samples[:, idx, :] = samples[:, idx, :] * 100.0
            elif ttype == 'log':
                samples[:, idx, :] = torch.expm1(samples[:, idx, :])

        series_results = {}

        for variate_idx, metadata in enumerate(variate_metadata):
            variate_samples = samples[:, variate_idx, :]  # Shape: (num_samples, horizon)
            variate_quantiles = {}

            for q in quantiles:
                quantile_values = []
                for time_idx in range(horizon):
                    time_samples = variate_samples[:, time_idx]  # Shape: (num_samples,)
                    quantile_value = torch.quantile(time_samples, q).item()
                    quantile_values.append(self._to_scalar(quantile_value))
                variate_quantiles[f"q{q:.2f}"] = quantile_values

            # Use variate_id as key to ensure uniqueness
            series_results[metadata['variate_id']] = {
                'quantiles': variate_quantiles,
                'metadata': metadata
            }

        return {
            'samples': samples,
            'series': series_results,
            'timestamps': future_timestamps,
            'variate_metadata': variate_metadata,
            'horizon': horizon,
            'time_interval_seconds': time_interval
        }

    def _run_toto_inference(self, masked_timeseries: MaskedTimeseries, horizon: int):
        """Run TOTO model inference on tensor data.

        Args:
            masked_timeseries: Input tensor data
            horizon: Number of future steps to predict

        Returns:
            TOTO forecast result object
        """
        if not self._model_loaded:
            raise RuntimeError("TOTO model not loaded. Call _ensure_model_loaded() first.")

        try:
            forecast_result = self._forecaster.forecast(
                masked_timeseries,
                # We can set any number of timesteps into the future that we'd like to forecast. Because Toto is an autoregressive model,
                # the inference time will be longer for longer forecasts.
                prediction_length=horizon,
                # TOTOForecaster draws samples from a predicted parametric distribution. The more samples, the more stable and accurate the prediction.
                # This is especially important if you care about accurate prediction intervals in the tails.
                num_samples=self.config.get("num_samples", 256),
                # TOTOForecaster also handles batching the samples in order to control memory usage.
                # Set samples_per_batch as high as you can without getting OOMs for maximum performance.
                # If you're doing batch inference, the effective batch size sent to the model is (batch_size x samples_per_batch).
                samples_per_batch=self.config.get("samples_per_batch", 256),
                # KV cache should significantly speed up inference, and in most cases should reduce memory usage too.
                use_kv_cache=self.config.get("use_kv_cache", True),
            )

            return forecast_result

        except Exception as e:
            self.logger.error(f"TOTO inference failed: {str(e)}")
            raise

    def _to_scalar(self, x):
        """Return plain float from numpy/PyTorch scalar or array."""
        if isinstance(x, np.ndarray):
            return float(x.reshape(-1)[0])
        return float(x)

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model."""
        if not self._model_loaded:
            return {"status": "not_loaded"}

        checkpoint = self.config.get("checkpoint", "Datadog/Toto-Open-Base-1.0")
        model_path = os.path.join(self.model_cache_dir, checkpoint.replace("/", "_"))

        return {
            "status": "loaded",
            "checkpoint": checkpoint,
            "device": str(next(self._model.parameters()).device) if self._model else "unknown"
        }
