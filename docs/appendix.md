# Technical Appendix: Forecasting Agent Analysis

This document provides a comprehensive technical analysis of the forecasting agent project, examining the challenges, trade-offs, and architectural decisions made during development. It covers model comparisons, data format requirements, infrastructure limitations, and the practical realities of implementing time series forecasting systems.

## 1. Model Comparison: Prophet vs NBEATS vs TOTO

### 1.1 Overview

| Model | Type | Strengths | Weaknesses | Best Use Case |
|-------|------|-----------|------------|---------------|
| **Prophet** | Statistical | Easy to use, handles seasonality well, interpretable | Limited to univariate, requires domain knowledge for holidays | Business metrics with clear seasonal patterns |
| **NBEATS** | Deep Learning | Multivariate, no feature engineering, good accuracy | Requires substantial training data, black box | Complex time series with multiple variables |
| **TOTO** | Transformer | Zero-shot learning, handles diverse patterns, pre-trained | Limited documentation, experimental, resource intensive | Scenarios with limited historical data |

### 1.2 Detailed Analysis

#### Prophet (Facebook's Time Series Forecasting)
```python
# Prophet expects simple DataFrame format
df = pd.DataFrame({
    'ds': timestamps,  # datetime column
    'y': values       # target values
})
```

**Advantages:**
- Mature, well-documented library with extensive community support
- Built-in handling of holidays, seasonality, and trend changes
- Interpretable components (trend, seasonal, holiday effects)
- Robust to missing data and outliers
- Fast training and inference

**Limitations:**
- Univariate only (single target variable)
- Requires domain knowledge for holiday calendars
- Less effective for complex, non-linear patterns
- Limited multivariate capabilities

#### NBEATS (Neural Basis Expansion Analysis)
```python
# NBEATS requires Darts TimeSeries format
from darts import TimeSeries
ts = TimeSeries.from_dataframe(df, time_col='timestamp', value_cols=['cost', 'cpu', 'memory'])
```

**Advantages:**
- Multivariate forecasting (multiple metrics simultaneously)
- No manual feature engineering required
- State-of-the-art accuracy on many benchmarks
- Handles complex non-linear patterns
- Available through Darts library with good documentation

**Limitations:**
- Requires substantial training data (typically 100+ observations)
- Computationally intensive training process
- Black box model with limited interpretability
- Sensitive to hyperparameter tuning

#### TOTO (Datadog's Zero-Shot Forecasting)
```python
# TOTO requires tensor format with masking
from toto.dataset import MaskedTimeseries
masked_ts = MaskedTimeseries(
    values=torch.tensor(data),
    mask=torch.tensor(mask)
)
```

**Advantages:**
- Zero-shot learning
- Pre-trained on diverse time series patterns
- Handles multiple variables and irregular sampling
- Fast inference once loaded
- Good performance on limited data

**Limitations:**
- No official Python package (requires copying research code)
- Large model size
- Requires significant GPU memory for optimal performance

## 2. Data Format Requirements and Challenges

### 2.1 Format Incompatibilities

Each model requires fundamentally different input formats, creating significant engineering overhead:

#### Prophet Format
```python
# Simple DataFrame with specific column names
{
    'ds': '2024-01-01T00:00:00Z',  # Must be named 'ds'
    'y': 1.23                      # Must be named 'y'
}
```

#### Darts TimeSeries Format
```python
# Multi-dimensional DataFrame with datetime index
pd.DataFrame({
    'cost_usd': [1.23, 1.45, 1.67],
    'cpu_pct': [45.2, 47.8, 52.1],
    'mem_pct': [67.3, 69.1, 71.5]
}, index=pd.DatetimeIndex(['2024-01-01', '2024-01-02', '2024-01-03']))
```

#### TOTO Tensor Format
```python
# 3D tensor with explicit masking
{
    'values': torch.tensor([[[1.23, 1.45, 1.67],    # cost
                            [45.2, 47.8, 52.1],     # cpu
                            [67.3, 69.1, 71.5]]]),  # memory
    'mask': torch.tensor([[[True, True, True],
                          [True, True, True],
                          [True, True, True]]])
}
```

### 2.2 Adapter Pattern Implementation

To handle these incompatibilities, we implemented the Adapter pattern:

```python
class ForecastingAdapter:
    def convert_input(self, prometheus_data: Dict) -> ModelSpecificFormat:
        """Convert Prometheus data to model-specific format"""
        pass
    
    def generate_forecast(self, data: ModelSpecificFormat) -> Dict:
        """Generate forecast and return standardized JSON"""
        pass
```

This approach provides:
- **Consistent Interface**: All models expose the same API
- **Format Isolation**: Each adapter handles its specific requirements
- **Maintainability**: Easy to add new models without affecting existing code
- **Testing**: Each adapter can be tested independently

## 3. Prometheus and Time Series Database Limitations

### 3.1 The Future Timestamp Problem

**Core Issue**: Prometheus and most time series databases are designed for historical data collection, not future data storage.

#### Prometheus Limitations:
- **Ingestion Window**: Typically accepts data within a 1-2 hour window of current time
- **Future Rejection**: Explicitly rejects samples with timestamps more than 2 days in the future
- **Storage Design**: Optimized for append-only historical data, not future projections

### 3.2 VictoriaMetrics Analysis

Based on research into VictoriaMetrics capabilities:

#### Current Capabilities:
- **Extended Retention**: Better compression and longer retention than Prometheus
- **JSON Export**: Supports exporting data in JSON Lines format
- **MetricsQL**: Enhanced query language with forecasting functions like `keep_next_value()`
- **Scalability**: Better performance for large-scale deployments

#### Future Data Storage Investigation:
```json
// VictoriaMetrics JSON export format
{
  "metric": {"__name__": "forecast_cost", "cluster": "prod"},
  "values": [1.23, 1.45, 1.67],
  "timestamps": [1704067200000, 1704153600000, 1704240000000]
}
```

**Research Findings**:
- VictoriaMetrics has similar timestamp validation as Prometheus
- No native support for storing future timestamps
- Would require custom ingestion pipeline to bypass timestamp validation
- Potential workaround: Store forecasts with current timestamp + forecast_horizon label

### 3.3 JSON Export Solution

Given these limitations, we chose JSON export as the primary forecast delivery mechanism:

#### Advantages:
- **No Timestamp Restrictions**: Can include any future timestamps
- **Rich Metadata**: Support for quantiles, confidence intervals, model information
- **Database Agnostic**: Can be stored in any system (PostgreSQL, MongoDB, etc.)
- **API Friendly**: Direct consumption by web applications and dashboards

#### JSON Schema:
```json
{
  "cluster": "production",
  "generated_at": "2024-01-01T12:00:00Z",
  "forecast_horizon": 7,
  "model": "toto",
  "metrics": {
    "cost_usd": {
      "q0.10": [{"x": "2024-01-08T00:00:00Z", "y": 1.23}],
      "q0.50": [{"x": "2024-01-08T00:00:00Z", "y": 1.45}],
      "q0.90": [{"x": "2024-01-08T00:00:00Z", "y": 1.67}]
    }
  }
}
```

## 4. Domain Knowledge and Model Tuning Challenges

### 4.1 Current State: "Working but Not Optimized"

The current implementation successfully generates forecasts, but several areas require domain expertise for production optimization:

#### NBEATS Hyperparameters:
```yaml
nbeats:
  input_chunk_length: 24    # How many hours of history to use
  output_chunk_length: 24   # How many hours to forecast
  n_epochs: 50             # Training iterations
  num_stacks: 30           # Model complexity
  num_blocks: 1            # Architecture depth
  layer_widths: [512]      # Neural network width
```

**Tuning Challenges**:
- **Input Length**: Too short misses patterns, too long includes noise
- **Architecture Size**: Larger models may overfit on limited data
- **Training Time**: More epochs improve accuracy but increase training time
- **Seasonality**: Need to understand business cycles (daily, weekly, monthly)

#### TOTO Configuration:
```yaml
toto:
  context_length: 4096     # Maximum sequence length
  num_samples: 256         # Monte Carlo samples for uncertainty
  checkpoint: "Datadog/Toto-Open-Base-1.0"  # Pre-trained model
```

**Domain Considerations**:
- **Context Length**: Longer context captures more patterns but requires more memory
- **Sampling**: More samples improve uncertainty estimates but slow inference
- **Model Selection**: Different checkpoints may work better for specific domains

### 4.2 Production Readiness Gaps

#### Data Quality Requirements:
- **Missing Data Handling**: Need robust imputation strategies
- **Outlier Detection**: Automated detection and handling of anomalous values
- **Data Validation**: Ensure input data meets model assumptions

#### Model Monitoring:
- **Drift Detection**: Monitor when model performance degrades
- **Retraining Triggers**: Automated retraining when accuracy drops
- **A/B Testing**: Compare model performance across different configurations

#### Business Logic Integration:
- **Holiday Calendars**: Account for business-specific non-working days
- **Capacity Constraints**: Ensure forecasts respect physical limitations
- **Cost Models**: Integrate with actual pricing structures

## 5. Library Availability and Integration Challenges

### 5.1 The TOTO Integration Problem

#### Official Library Status:
- **No PyPI Package**: TOTO is not available as a standard Python package
- **Research Repository**: Only available as research code on GitHub
- **Dependency Management**: Complex dependency tree with specific version requirements
- **Documentation**: Limited to research papers and README files

#### Integration Approach:
```bash
# Current solution: Git submodule
git submodule add https://github.com/DataDog/toto.git
git submodule update --init --recursive
```

#### Code Copying Requirements:
We had to extract and adapt several components:

```python
# From toto/dataset.py
class MaskedTimeseries:
    """Copied and adapted from TOTO research repository"""
    def __init__(self, values, mask):
        self.values = values
        self.mask = mask

# From toto/forecaster.py  
class TotoForecaster:
    """Adapted forecasting logic from research code"""
    def __init__(self, checkpoint, device):
        # Implementation copied from research repo
        pass
```

### 5.2 Comparison with Established Libraries

#### Darts (NBEATS):
```python
# Clean, documented API
from darts.models import NBEATSModel
from darts import TimeSeries

model = NBEATSModel(
    input_chunk_length=24,
    output_chunk_length=12
)
model.fit(train_series)
forecast = model.predict(n=12)
```

**Advantages**:
- **PyPI Available**: `pip install darts`
- **Comprehensive Documentation**: Tutorials, examples, API reference
- **Active Community**: Regular updates, bug fixes, feature requests
- **Production Ready**: Used by many organizations in production

#### Prophet:
```python
# Simple, well-documented interface
from prophet import Prophet

model = Prophet()
model.fit(df)
forecast = model.predict(future_df)
```

**Advantages**:
- **Official Support**: Maintained by Meta (Facebook)
- **Extensive Documentation**: Books, courses, tutorials available
- **R and Python**: Available in both major data science languages
- **Industry Adoption**: Widely used in production environments

### 5.3 Risks and Mitigation Strategies

#### Current Risks:
1. **Code Maintenance**: TOTO code may become outdated or incompatible
2. **Security**: No official security updates or vulnerability patches

#### Long-term Solutions:
1. **Vendor Evaluation**: Consider commercial forecasting APIs (AWS Forecast, Azure Time Series Insights)
2. **Model Alternatives**: Evaluate other zero-shot models (TimeGPT, Chronos)
3. **Custom Implementation**: Develop domain-specific application like for Toto
