# How to Use the Financial Data Analyst Skill

This skill automatically analyzes financial and trading data to provide comprehensive performance metrics, technical indicators, risk analysis, and portfolio insights.

## Quick Start

The skill activates when you provide financial data and request analysis. You can attach CSV files, paste JSON data, or describe your data structure.

## Example Invocations

### Example 1: Trade Performance Analysis
```
I have a CSV file with my trade history. Can you analyze the performance and calculate Sharpe ratio, max drawdown, and win rate?
```

**What to provide:**
- Trade history CSV or JSON with entry/exit dates, prices, quantities
- Direction (long/short) for each trade
- Optional: Commission costs

**What you'll get:**
- Sharpe and Sortino ratios
- Maximum drawdown analysis
- Win rate and profit factor
- Average win/loss metrics
- Trade expectancy
- Performance interpretation

---

### Example 2: Technical Indicators
```
Calculate RSI, MACD, and Bollinger Bands for this stock data and tell me if there are any trading signals.
```

**What to provide:**
- OHLCV data (Open, High, Low, Close, Volume)
- CSV, JSON, or description of price data
- Timeframe information (daily, hourly, etc.)

**What you'll get:**
- RSI values with overbought/oversold signals
- MACD line, signal line, and histogram
- Bollinger Bands (upper, middle, lower)
- Moving averages (SMA, EMA)
- ATR and Stochastic Oscillator
- Trading signal interpretations

---

### Example 3: Risk Analysis
```
Analyze the risk of this portfolio and calculate VaR at 95% confidence level.
```

**What to provide:**
- Return series (daily, weekly, or monthly returns)
- Optional: Benchmark returns for beta calculation
- Risk-free rate (if different from default 2%)

**What you'll get:**
- Value at Risk (VaR) at 95% and 99%
- Conditional VaR (CVaR)
- Volatility metrics (historical, annualized)
- Beta and correlation to benchmark
- Sharpe, Sortino, and Calmar ratios
- Risk interpretation and recommendations

---

### Example 4: Portfolio Analysis
```
Analyze the correlation between these assets and suggest optimal portfolio weights.
```

**What to provide:**
- Return series for each asset in portfolio
- Current portfolio weights (or equal weights assumed)
- Asset names/tickers

**What you'll get:**
- Correlation matrix with heatmap
- Diversification ratio
- Concentration risk metrics
- Optimal weights (Sharpe maximization)
- Minimum variance weights
- Portfolio volatility and expected return

---

### Example 5: Backtest Analysis
```
I backtested a trading strategy. Can you analyze the equity curve and calculate performance metrics?
```

**What to provide:**
- Trade history with all trades
- Initial capital amount
- Trading period dates

**What you'll get:**
- Equity curve analysis
- Drawdown periods and recovery
- Monthly/yearly return breakdown
- Risk-adjusted performance metrics
- Statistical significance tests
- Strategy evaluation

---

## Data Formats Accepted

### CSV Files
```csv
date,open,high,low,close,volume
2024-01-02,150.0,152.5,149.5,151.0,1000000
2024-01-03,151.0,153.0,150.0,152.5,1100000
```

### JSON Data
```json
{
  "trades": [
    {
      "entry_date": "2024-01-05",
      "exit_date": "2024-01-10",
      "entry_price": 150.00,
      "exit_price": 155.50,
      "quantity": 100,
      "direction": "long"
    }
  ]
}
```

### Text Description
```
I have daily stock data from Jan 1 to Dec 31, 2024:
- Starting price: $100
- Ending price: $125
- Max price: $130
- Min price: $95
```

---

## Tips for Best Results

1. **Include All Relevant Data**: Provide complete trade history, OHLCV data, or return series
2. **Specify Timeframe**: Mention if data is daily, hourly, weekly, etc.
3. **Include Trading Costs**: Add commission/slippage for realistic backtesting
4. **Provide Context**: Mention asset class, strategy type, or investment goals
5. **Ask Specific Questions**: Request particular metrics or analysis types you need
6. **Multiple Assets**: For portfolio analysis, provide data for all holdings

---

## Common Use Cases

### For Day Traders
- Calculate technical indicators for entry/exit signals
- Analyze intraday volatility with ATR
- Monitor momentum with RSI and Stochastic

### For Swing Traders
- Evaluate trade performance metrics
- Analyze win rate and profit factor
- Calculate optimal position sizing

### For Portfolio Managers
- Monitor portfolio correlation and diversification
- Calculate risk-adjusted returns
- Optimize portfolio weights

### For Quant Traders
- Backtest strategy performance
- Calculate statistical significance
- Analyze drawdown characteristics

### For Risk Managers
- Calculate VaR and CVaR
- Monitor portfolio volatility
- Assess tail risk exposure

---

## Integration Examples

### With CSV Upload
```
I'm uploading trades.csv with 100 trades from last quarter.
Can you analyze performance and compare to S&P 500?
```

### With Live Data Description
```
Today AAPL closed at $175.50 after hitting a high of $177.
RSI yesterday was 68. What's today's RSI and any signals?
```

### With Multiple Analyses
```
I have both trade history and OHLCV data.
First, calculate my strategy's Sharpe ratio.
Then, show me if RSI and MACD confirm current positions.
```

---

## What NOT to Expect

- Real-time streaming data analysis (provide snapshots instead)
- Investment advice or recommendations (analysis only)
- Execution of trades (analysis tool, not trading system)
- Tax reporting (use tax-specific software)
- Options/derivatives pricing (unless you provide price data)

---

## Sample Files

The skill includes sample data files you can reference:
- `sample_trade_history.json` - Example trade data format
- `sample_ohlcv_data.json` - Example OHLCV data format
- `sample_portfolio_data.json` - Example portfolio data format

---

## Need Help?

Ask the skill to:
- Explain any metric or indicator
- Compare different analysis approaches
- Suggest appropriate metrics for your situation
- Interpret complex results in plain language

Example: "What does a Sharpe ratio of 1.8 mean?" or "Is my portfolio well diversified?"
