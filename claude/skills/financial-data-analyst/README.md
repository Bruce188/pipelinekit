# Financial Data Analyst Skill

A comprehensive Claude Code skill for analyzing financial and trading data with Python-based calculations.

## Overview

This skill provides professional-grade financial analysis capabilities including:
- Trading performance metrics (Sharpe, Sortino, max drawdown, profit factor)
- Technical indicators (RSI, MACD, Bollinger Bands, moving averages)
- Risk analysis (VaR, CVaR, volatility, beta)
- Portfolio analytics (correlation, diversification, optimal weights)

## Installation

### For Claude Code (Project-Level)
```bash
# Copy skill to your project
cp -r financial-data-analyst /path/to/your/project/.claude/skills/
```

### For Claude Code (User-Level)
```bash
# Already installed at:
~/.claude/skills/financial-data-analyst/
```

### For Claude Desktop
1. Create a ZIP file: `zip -r financial-data-analyst.zip financial-data-analyst/`
2. Drag and drop the ZIP into Claude Desktop

## Skill Structure

```
financial-data-analyst/
├── SKILL.md                      # Main skill definition
├── README.md                     # This file
├── HOW_TO_USE.md                # Usage examples and guide
├── analyze_trades.py            # Trade performance analysis
├── calculate_indicators.py      # Technical indicators
├── risk_metrics.py              # Risk analysis calculations
├── portfolio_analysis.py        # Portfolio metrics
├── sample_trade_history.json    # Example trade data
├── sample_ohlcv_data.json      # Example OHLCV data
└── sample_portfolio_data.json  # Example portfolio data
```

## Python Dependencies

The skill uses standard Python libraries that are typically pre-installed:
- `math` (standard library)
- `json` (standard library)
- `typing` (standard library)
- `datetime` (standard library)

Optional libraries for enhanced functionality:
- `pandas` - For CSV/Excel data processing
- `numpy` - For advanced numerical operations
- `matplotlib` - For visualizations
- `pandas-ta` or `ta-lib` - For additional technical indicators

**Note**: The skill works without optional libraries. Claude will suggest installing them if needed for specific analyses.

## Quick Start

1. **Provide Data**: Share CSV file, JSON data, or describe your financial data
2. **Request Analysis**: Ask for specific metrics or comprehensive analysis
3. **Review Results**: Examine calculated metrics and interpretations

Example:
```
I have a CSV with trade history. Can you calculate the Sharpe ratio and max drawdown?
```

## Features

### 1. Trade Performance Analysis
- Sharpe and Sortino ratios
- Maximum drawdown calculation
- Win rate and profit factor
- Average win/loss metrics
- Trade expectancy
- Statistical significance

### 2. Technical Indicators
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands
- Moving Averages (SMA, EMA)
- ATR (Average True Range)
- Stochastic Oscillator
- Trading signals

### 3. Risk Metrics
- Value at Risk (VaR)
- Conditional VaR (CVaR)
- Volatility analysis
- Beta calculation
- Downside deviation
- Risk-adjusted returns

### 4. Portfolio Analysis
- Correlation matrices
- Diversification ratio
- Concentration risk
- Optimal weights (Sharpe maximization)
- Minimum variance portfolio
- Portfolio volatility

## Usage Examples

### Analyze Trade Performance
```
Analyze this trade history and calculate performance metrics:
[Attach CSV or paste JSON]
```

### Calculate Technical Indicators
```
Calculate RSI, MACD, and Bollinger Bands for this stock data:
[Provide OHLCV data]
```

### Risk Analysis
```
Calculate VaR at 95% confidence for this portfolio:
[Provide returns data]
```

### Portfolio Optimization
```
Analyze correlation between these assets and suggest optimal weights:
[Provide asset returns]
```

## Sample Data

The skill includes three sample data files for reference:

1. **sample_trade_history.json** - Example trade data with 5 trades
2. **sample_ohlcv_data.json** - Example OHLCV data with 22 periods
3. **sample_portfolio_data.json** - Example portfolio with 4 assets

## Limitations

- Requires historical data (not real-time streaming)
- Does not execute trades or connect to brokers
- Past performance doesn't guarantee future results
- Assumes properly adjusted price data (splits, dividends)
- Not suitable for tax reporting or regulatory compliance

## Best Practices

1. Include all trading costs (commissions, slippage)
2. Use appropriate risk-free rate for your region
3. Ensure data completeness (no gaps in time series)
4. Provide sufficient data points (minimum 30, ideally 100+)
5. Specify timeframe clearly (daily, hourly, etc.)

## Troubleshooting

**Issue**: Skill doesn't activate
- **Solution**: Use keywords like "analyze trading data", "calculate metrics", "performance analysis"

**Issue**: Missing data error
- **Solution**: Ensure all required fields are present (dates, prices, quantities)

**Issue**: Incorrect calculations
- **Solution**: Verify data format and check for data quality issues

**Issue**: Need different indicators
- **Solution**: Ask for specific technical indicators by name

## Support

For questions or issues:
1. Check HOW_TO_USE.md for detailed examples
2. Review sample data files for format reference
3. Ask Claude to explain any metric or calculation

## Version

- **Version**: 1.0.0
- **Last Updated**: 2025-11-12
- **Compatible With**: Claude Code, Claude Desktop, Claude API

## License

This skill is provided as-is for financial analysis purposes. Not financial advice.

## Contributing

To enhance this skill:
1. Add new indicators in `calculate_indicators.py`
2. Add new risk metrics in `risk_metrics.py`
3. Extend portfolio analysis in `portfolio_analysis.py`
4. Add new sample data for different scenarios

## Acknowledgments

Built using the Claude Code Skills Factory framework.
Based on industry-standard financial analysis methodologies.
