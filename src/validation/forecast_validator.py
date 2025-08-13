"""Validation utilities for TOTO forecasts."""
from __future__ import annotations

from typing import Dict, Any, List, Optional
import logging
import numpy as np
import torch

from adapters.forecasting.toto_adapter import TOTOAdapter
from toto.data.util.dataset import MaskedTimeseries

logger = logging.getLogger(__name__)


class ForecastValidator:
    """Compute accuracy metrics for TOTO forecasts."""

    def __init__(self, train_ratio: float = 0.7):
        if not 0 < train_ratio < 1:
            raise ValueError("train_ratio must be in (0, 1)")
        self.train_ratio = train_ratio

    def validate(
        self,
        raw_prometheus_data: Dict[str, Any],
        prometheus_adapter, 
        model_config: Dict[str, Any],
        cluster_names: List[str],
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """Run validation across clusters.

        Returns a nested dict::

            {
              "cluster_name": {
                 "metric_variate_id": {"mape": .., "mae": .., "rmse": ..},
                 ...
              },
              ...
            }
        """
        results: Dict[str, Dict[str, Dict[str, float]]] = {}
        toto_adapter = TOTOAdapter(model_config)

        for cluster in cluster_names:
            try:
                converted = prometheus_adapter.convert_to_toto_format(
                    raw_prometheus_data, cluster
                )
                mts: MaskedTimeseries = converted["masked_timeseries"]
                variate_metadata: List[Dict[str, str]] = converted["variate_metadata"]

                cluster_scores = self._validate_cluster(
                    mts, variate_metadata, toto_adapter, model_config
                )
                results[cluster] = cluster_scores
            except Exception as exc:  # noqa: BLE001 – we surface error message
                logger.error("Validation failed for cluster %s: %s", cluster, exc)
                results[cluster] = {"error": str(exc)}

        return results

    def _validate_cluster(
        self,
        mts: MaskedTimeseries,
        variate_metadata: List[Dict[str, str]],
        toto_adapter: TOTOAdapter,
        model_config: Dict[str, Any],
    ) -> Dict[str, Dict[str, float]]:
        """Validate a single cluster across all variates."""
        n_timesteps = mts.series.shape[1]
        if n_timesteps < 4:
            raise ValueError("Insufficient history (need >=4 timesteps)")

        half_len = n_timesteps // 2
        train_len = int(half_len * self.train_ratio)
        horizon = half_len - train_len
        if horizon == 0:
            raise ValueError("train_ratio too high; no validation horizon")

        # Slice tensors: keep all variates, only first train_len timesteps
        train_slice = mts.series[:, :train_len]
        pad_slice = mts.padding_mask[:, :train_len]
        id_slice = mts.id_mask[:, :train_len]
        ts_slice = mts.timestamp_seconds[:, :train_len]

        # Assemble new MaskedTimeseries object
        mts_train = MaskedTimeseries(
            train_slice,
            pad_slice,
            id_slice,
            ts_slice,
            mts.time_interval_seconds,
        )

        forecast = toto_adapter.forecast(
            mts_train, horizon=horizon, quantiles=model_config.get("quantiles"), variate_metadata=variate_metadata
        )
        # use median (q0.50) if available else mean of samples
        preds = self._extract_point_forecast(forecast)

        actual_slice = mts.series[:, train_len:train_len + horizon]
        scores: Dict[str, Dict[str, float]] = {}
        for idx, meta in enumerate(variate_metadata):
            pred = preds[idx]
            truth = actual_slice[idx].cpu().numpy()
            scores[meta["variate_id"]] = self._compute_metrics(pred, truth)
        return scores

    @staticmethod
    def _compute_metrics(pred: np.ndarray, actual: np.ndarray) -> Dict[str, float]:
        mae = float(np.mean(np.abs(pred - actual)))

        # exclude very small actual values to avoid division blow-ups
        # Determine dynamic epsilon as 1% of median absolute actual (or fallback to 1e-2)
        median_abs = np.median(np.abs(actual))
        epsilon = max(0.01 * median_abs, 1e-2)

        mask = np.abs(actual) > epsilon
        if mask.any():
            mape = float(np.mean(np.abs((actual[mask] - pred[mask]) / actual[mask])) * 100)
        else:
            mape = float("nan")

        rmse = float(np.sqrt(np.mean((pred - actual) ** 2)))
        return {"mae": mae, "mape": mape, "rmse": rmse}

    @staticmethod
    def _extract_point_forecast(forecast_dict: Dict[str, Any]) -> np.ndarray:
        """Return numpy array of shape (n_variates, horizon) with point forecasts."""
        if "series" in forecast_dict:
            horizon = forecast_dict["horizon"]
            n_variates = len(forecast_dict["series"])
            preds = np.zeros((n_variates, horizon), dtype=np.float32)
            for idx, (var_id, entry) in enumerate(forecast_dict["series"].items()):
                if "q0.50" in entry["quantiles"]:
                    preds[idx] = np.array(entry["quantiles"]["q0.50"], dtype=np.float32)
                else:
                    # mean across samples for each timestep
                    preds[idx] = forecast_dict["samples"][:, idx, :].mean(axis=0)
            return preds
        raise ValueError("Malformed forecast result")
