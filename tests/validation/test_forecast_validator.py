import numpy as np

import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from validation.forecast_validator import ForecastValidator


def test_compute_metrics_simple():
    pred = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    actual = np.array([1.0, 2.0, 4.0], dtype=np.float32)

    metrics = ForecastValidator._compute_metrics(pred, actual)

    # MAE: (0 + 0 + 1) / 3 = 0.333...
    assert abs(metrics["mae"] - 0.3333) < 1e-3

    # MAPE: last element percentage error 25%
    assert abs(metrics["mape"] - 8.3333) < 1e-2

    # RMSE: sqrt((0 + 0 + 1)/3) = 0.577...
    assert abs(metrics["rmse"] - 0.57735) < 1e-3
