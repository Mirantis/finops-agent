import pandas as pd
import numpy as np
from darts.models import Prophet as DartsProphet
from darts import TimeSeries
from core.forecasting import ForecastingModel

class ProphetAdapter(ForecastingModel):
    def __init__(self, config):
        self.config = config
        self.model = DartsProphet(**config)
        self.fitted = False
        self.train_series = None

    def fit(self, df: pd.DataFrame):
        # df: columns ['ds', 'y']
        freq = pd.infer_freq(df['ds'])
        if freq is None:
            raise ValueError("Could not infer frequency from the 'ds' column. Please ensure your data is regularly spaced.")
        series = TimeSeries.from_dataframe(df, time_col='ds', value_cols='y', fill_missing_dates=True, freq=freq)
        self.model.fit(series)
        self.fitted = True
        self.train_series = series

    def forecast(self, horizon: int, frequency: str = 'D') -> dict:
        if not self.fitted:
            raise RuntimeError("Model must be fit before forecasting.")
        forecast = self.model.predict(horizon)
        # Darts Prophet provides prediction intervals via predict(..., num_samples=100)
        quantiles = self.model.predict(horizon, num_samples=100, return_pred_int=True)
        # quantiles is a tuple: (forecast, lower, upper)
        # But for Darts >=0.25, quantiles is a dict with keys 'lower', 'upper'
        if isinstance(quantiles, tuple):
            lower = quantiles[1]
            upper = quantiles[2]
        else:
            lower = quantiles['lower']
            upper = quantiles['upper']
        forecast_df = forecast.pd_dataframe().reset_index().rename(columns={'time': 'ds', forecast.columns[0]: 'value'})
        lower_df = lower.pd_dataframe().reset_index().rename(columns={'time': 'ds', lower.columns[0]: 'value'})
        upper_df = upper.pd_dataframe().reset_index().rename(columns={'time': 'ds', upper.columns[0]: 'value'})
        return {
            'forecast': forecast_df,
            'lower_bound': lower_df,
            'upper_bound': upper_df,
            'prophet_forecast': forecast_df
        }

    def evaluate(self, test_data: pd.DataFrame, metrics: list = None) -> dict:
        if metrics is None:
            metrics = ['mae', 'rmse', 'mape']
        test_series = TimeSeries.from_dataframe(test_data, time_col='ds', value_cols='y')
        y_true = test_series.values().flatten()
        y_pred = self.model.predict(len(y_true)).values().flatten()
        results = {}
        if 'mae' in metrics:
            results['mae'] = np.mean(np.abs(y_true - y_pred))
        if 'rmse' in metrics:
            results['rmse'] = np.sqrt(np.mean((y_true - y_pred) ** 2))
        if 'mape' in metrics:
            results['mape'] = np.mean(np.abs((y_true - y_pred) / np.maximum(np.abs(y_true), 1e-8))) * 100
        return results
