# FinOps Agent — Risk, ROI, and Safety

## What it is today

The FinOps Agent is an AI-powered forecasting tool with deterministic optimization algorithms to provide recommendations for cloud infrastructure cost & resource usage reduction.

The current model is designed to be an evidence-based co-pilot for the operator, not an autonomous driver. It provides insights while ensuring you are always in full control.

- **Forecasting model**: Uses the TOTO time‑series model to produce short‑term forecasts from historical metrics.
- **Validation**: Performs a backtest by training on the first ~70% of a known series and testing on the last ~30%.
- **Error metrics**: Reports MAPE, MAE, and RMSE for backtests to quantify forecast accuracy.
- **Data inputs**: Designed to work with cluster telemetry and cost data (e.g., Prometheus metrics and OpenCost exports).
- **Recommendation mode**: Produces advisory suggestions based on deterministic optimization algorithms for manual review.

## How we reduce bad suggestions today

- **Authoritative data**: Uses measured telemetry and cost exports as inputs.
- **Evidence with outputs**: Each suggestion includes the window used, forecast horizon, and error metrics from the most recent backtest.
- **Human review**: Suggestions require manual review/approval downstream. No autonomous bulk actions.

## Measuring value today

- **Transparent baselines**: Surfaces recent usage/cost snapshots alongside forecasts to aid manual evaluation of potential savings.
- **Accuracy first**: Focus is on forecast quality (MAPE/MAE/RMSE) and clear assumptions before any cost action is considered.

## Safety and boundaries today

- **Advisory only**: The system does not delete, resize, or reconfigure infrastructure on its own.
- **Operator control**: Any operational change is executed outside the agent by the operator’s existing workflows/tools.

## Future enhancements

- Generalize beyond idle-capacity optimisation recommendations to scenario-based cost deltas across change types (e.g., right-sizing).

- SLO‑aware constraints:
  - Each recommendation ships `{training_window, horizon_days, quantile_used, prediction_band, backtest_metrics, guardrails_passed, rationale}`

- ROI
  - Track predicted vs realized savings with confidence bands; maintain an auditable change log.
  - Calibration monitoring: Track p10/p90 coverage and alert on drift.
  - Pre-hoc what-if scenarios for right-sizing/idle cleanup; post-hoc compare predicted vs realized savings with audit trail.
