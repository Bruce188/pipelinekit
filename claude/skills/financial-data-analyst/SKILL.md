---
name: financial-data-analyst
description: Automatically analyzes financial and trading data using Python to calculate performance metrics, technical indicators, risk analysis, and portfolio statistics with visualizations
---

# Financial Data Analyst

This skill provides comprehensive financial and trading data analysis capabilities using Python-based calculations. It automatically processes OHLCV data, trade histories, and portfolio information to generate performance metrics, technical indicators, risk assessments, and visualizations.

## Capabilities

- **Trading Performance Analysis**: Calculate Sharpe ratio, Sortino ratio, maximum drawdown, win rate, profit factor, average win/loss, and return statistics
- **Technical Indicators**: Compute RSI, MACD, Bollinger Bands, moving averages (SMA, EMA), ATR, Stochastic Oscillator, and momentum indicators
- **Risk Metrics**: Calculate Value at Risk (VaR), Conditional VaR (CVaR), beta, volatility, downside deviation, and risk-adjusted returns
- **Portfolio Analysis**: Analyze correlation matrices, diversification metrics, asset allocation, portfolio variance, and optimal weights
- **Backtesting Analysis**: Evaluate strategy performance with equity curves, drawdown analysis, monthly/yearly returns, and statistical validation
- **Data Visualization**: Generate charts and plots for performance metrics, indicator overlays, equity curves, and correlation heatmaps
- **Position Sizing**: Calculate position sizes based on risk parameters, Kelly Criterion, fixed fractional, and volatility-based methods

## Input Requirements

The skill accepts multiple data formats:

### OHLCV Data
- **Format**: CSV, JSON, or pandas DataFrame description
- **Required fields**: Date/Timestamp, Open, High, Low, Close, Volume
- **Optional fields**: Adjusted Close, Dividends, Splits
- **Frequency**: Any timeframe (1min, 5min, 1hour, daily, etc.)

### Trade History
- **Format**: CSV, JSON, or structured text
- **Required fields**: Entry date, exit date, entry price, exit price, quantity, direction (long/short)
- **Optional fields**: Commission, slippage, stop loss, take profit, trade notes

### Portfolio Data
- **Format**: CSV or JSON with asset allocations
- **Required fields**: Asset ticker/name, position size, entry price, current price
- **Optional fields**: Asset class, sector, country, weight

### Market Data
- **Format**: Benchmark returns for comparison (S&P 500, etc.)
- **Required fields**: Date, benchmark return or price

## Output Formats

The skill produces comprehensive analysis results:

### Performance Metrics Report
- Total return, annualized return, CAGR
- Sharpe ratio, Sortino ratio, Calmar ratio
- Maximum drawdown, average drawdown, recovery period
- Win rate, profit factor, expectancy
- Best/worst trade, average win/loss
- Statistical significance tests

### Technical Analysis
- Calculated indicator values with timestamps
- Signal generation (buy/sell/neutral)
- Indicator interpretation and recommendations
- Multi-timeframe analysis results

### Risk Analysis
- VaR and CVaR at different confidence levels (95%, 99%)
- Volatility metrics (historical, realized, implied)
- Beta and correlation to benchmark
- Risk-adjusted performance metrics
- Tail risk analysis

### Portfolio Metrics
- Correlation matrix (numerical and heatmap)
- Diversification ratio and effective number of assets
- Portfolio variance and standard deviation
- Optimal portfolio weights (Sharpe optimization, minimum variance)
- Concentration risk analysis

### Visualizations
- Equity curve with drawdown overlay
- Technical indicator charts with price
- Correlation heatmap
- Monthly/yearly return tables
- Risk/return scatter plots
- Distribution histograms

## How to Use

Invoke the skill when you need financial or trading data analysis:

**General invocation:**
"Analyze this trading data and calculate performance metrics"
"Calculate technical indicators for this OHLCV data"
"Perform risk analysis on this portfolio"
"Backtest this strategy and show me the results"

**Specific examples:**
"Calculate Sharpe ratio and max drawdown from this trade history CSV"
"Generate RSI, MACD, and Bollinger Bands for this stock data"
"Analyze the correlation between these portfolio assets"
"What's the VaR at 95% confidence for this portfolio?"
"Calculate optimal position sizing using the Kelly Criterion"

## Scripts

The skill includes four Python modules:

- **analyze_trades.py**: Analyzes trade history and calculates comprehensive performance metrics including Sharpe ratio, max drawdown, win rate, profit factor, and statistical tests
- **calculate_indicators.py**: Calculates technical indicators from OHLCV data including RSI, MACD, Bollinger Bands, moving averages, and generates trading signals
- **risk_metrics.py**: Computes risk metrics including VaR, CVaR, volatility, beta, downside deviation, and risk-adjusted performance measures
- **portfolio_analysis.py**: Analyzes portfolio composition with correlation matrices, diversification metrics, optimal weights, and concentration risk analysis

## Technical Requirements

### Python Libraries
The skill uses these libraries (installed automatically when needed):
- **pandas**: Data manipulation and analysis
- **numpy**: Numerical computations
- **scipy**: Statistical analysis and optimization
- **matplotlib**: Static visualizations
- **seaborn**: Statistical data visualization
- **pandas-ta** or **ta-lib**: Technical analysis indicators

### Data Quality Expectations
- Clean OHLCV data without gaps (or gaps handled appropriately)
- Trade history with consistent date formats
- Prices in decimal format (not strings)
- Reasonable data frequency (avoid mixing daily with intraday without adjustment)
- Sufficient data points for meaningful analysis (minimum 30 data points, ideally 100+)

## Best Practices

1. **Data Validation**: Always verify data completeness and format before analysis
2. **Risk-Free Rate**: Specify appropriate risk-free rate for Sharpe/Sortino calculations (default: 0% or 2%)
3. **Benchmark Selection**: Use relevant benchmark for beta and comparison (S&P 500 for stocks, appropriate index for other assets)
4. **Timeframe Consistency**: Ensure all data uses consistent timeframes (don't mix daily with minute data)
5. **Commission Inclusion**: Include trading costs for realistic backtesting results
6. **Sample Size**: Ensure sufficient data for statistical validity (at least 30 trades, 100+ data points)
7. **Survivorship Bias**: Be aware of survivorship bias in historical data
8. **Look-Ahead Bias**: Avoid using future information in backtesting calculations

## Limitations

### Data Limitations
- Requires accurate historical data (garbage in, garbage out)
- Cannot analyze real-time streaming data (use historical snapshots)
- Limited to provided data timeframe (cannot extrapolate beyond)
- Assumes data is properly adjusted for splits and dividends

### Analysis Constraints
- Past performance does not guarantee future results
- Statistical measures assume certain distribution properties (may not hold in reality)
- Technical indicators are lagging by nature
- Correlation does not imply causation
- Black swan events are not predicted by historical metrics

### Scope Boundaries
- Does not provide investment advice or recommendations
- Does not execute trades or connect to brokers
- Does not handle options, futures, or complex derivatives (unless provided as price data)
- Does not perform fundamental analysis or company research
- Does not account for tax implications

### When NOT to Use
- For real-time trading signals (use specialized trading systems)
- For regulatory compliance reporting (use certified software)
- For tax reporting (use tax-specific tools)
- As sole basis for investment decisions (combine with other analysis)
- For high-frequency trading analysis (requires specialized infrastructure)

## Example Workflow

1. **Provide Data**: Share CSV file or describe OHLCV data
2. **Specify Analysis**: Request specific metrics or comprehensive analysis
3. **Review Results**: Examine calculated metrics and interpretations
4. **Request Visualizations**: Ask for specific charts or plots
5. **Iterate**: Refine analysis based on initial results

## Integration with Other Skills

This skill works well with:
- **Data extraction skills**: For fetching financial data from APIs
- **Reporting skills**: For formatting analysis into professional reports
- **Visualization skills**: For creating presentation-ready charts
- **Portfolio optimization skills**: For advanced portfolio construction

## Version

Current version: 1.0.0
Last updated: 2025-11-12
