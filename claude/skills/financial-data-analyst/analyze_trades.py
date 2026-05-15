"""
Trade Performance Analysis Module

Analyzes trade history data and calculates comprehensive performance metrics
including Sharpe ratio, maximum drawdown, win rate, profit factor, and statistical tests.
"""

from typing import Dict, List, Any, Optional, Tuple
import json
from datetime import datetime, timedelta
import math


class TradeAnalyzer:
    """Analyze trade history and calculate performance metrics."""

    def __init__(self, trades_data: List[Dict[str, Any]], risk_free_rate: float = 0.02):
        """
        Initialize with trade history data.

        Args:
            trades_data: List of trade dictionaries with fields:
                - entry_date: Entry timestamp
                - exit_date: Exit timestamp
                - entry_price: Entry price
                - exit_price: Exit price
                - quantity: Position size
                - direction: 'long' or 'short'
                - commission: Trading costs (optional)
            risk_free_rate: Annual risk-free rate for Sharpe calculations (default: 2%)
        """
        self.trades = trades_data
        self.risk_free_rate = risk_free_rate
        self.metrics = {}
        self._process_trades()

    def _process_trades(self):
        """Process raw trade data and calculate returns."""
        self.returns = []
        self.pnl_values = []

        for trade in self.trades:
            direction = trade.get('direction', 'long').lower()
            entry_price = float(trade.get('entry_price', 0))
            exit_price = float(trade.get('exit_price', 0))
            quantity = float(trade.get('quantity', 1))
            commission = float(trade.get('commission', 0))

            if direction == 'long':
                pnl = (exit_price - entry_price) * quantity - commission
                ret = (exit_price - entry_price) / entry_price if entry_price > 0 else 0
            else:  # short
                pnl = (entry_price - exit_price) * quantity - commission
                ret = (entry_price - exit_price) / entry_price if entry_price > 0 else 0

            self.returns.append(ret)
            self.pnl_values.append(pnl)

    def safe_divide(self, numerator: float, denominator: float, default: float = 0.0) -> float:
        """Safely divide two numbers, returning default if denominator is zero."""
        if denominator == 0 or math.isnan(denominator) or math.isinf(denominator):
            return default
        result = numerator / denominator
        return result if not (math.isnan(result) or math.isinf(result)) else default

    def calculate_basic_metrics(self) -> Dict[str, Any]:
        """Calculate basic performance metrics."""
        if not self.returns:
            return {}

        total_trades = len(self.returns)
        winning_trades = [r for r in self.returns if r > 0]
        losing_trades = [r for r in self.returns if r < 0]

        win_count = len(winning_trades)
        loss_count = len(losing_trades)

        total_return = sum(self.returns)
        total_pnl = sum(self.pnl_values)

        avg_win = sum(winning_trades) / win_count if win_count > 0 else 0
        avg_loss = sum(losing_trades) / loss_count if loss_count > 0 else 0

        win_rate = self.safe_divide(win_count, total_trades)

        return {
            'total_trades': total_trades,
            'winning_trades': win_count,
            'losing_trades': loss_count,
            'win_rate': win_rate,
            'total_return': total_return,
            'total_pnl': total_pnl,
            'average_return': total_return / total_trades if total_trades > 0 else 0,
            'average_pnl': total_pnl / total_trades if total_trades > 0 else 0,
            'average_win': avg_win,
            'average_loss': avg_loss,
            'best_trade': max(self.returns) if self.returns else 0,
            'worst_trade': min(self.returns) if self.returns else 0,
            'largest_win_pnl': max(self.pnl_values) if self.pnl_values else 0,
            'largest_loss_pnl': min(self.pnl_values) if self.pnl_values else 0
        }

    def calculate_profit_factor(self) -> float:
        """Calculate profit factor (gross profits / gross losses)."""
        gross_profit = sum([p for p in self.pnl_values if p > 0])
        gross_loss = abs(sum([p for p in self.pnl_values if p < 0]))
        return self.safe_divide(gross_profit, gross_loss, default=0)

    def calculate_sharpe_ratio(self, periods_per_year: int = 252) -> float:
        """
        Calculate Sharpe ratio.

        Args:
            periods_per_year: Number of trading periods per year (252 for daily, 52 for weekly)

        Returns:
            Sharpe ratio
        """
        if not self.returns or len(self.returns) < 2:
            return 0

        mean_return = sum(self.returns) / len(self.returns)

        # Calculate standard deviation
        variance = sum((r - mean_return) ** 2 for r in self.returns) / (len(self.returns) - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0

        if std_dev == 0:
            return 0

        # Annualize
        annual_return = mean_return * periods_per_year
        annual_std = std_dev * math.sqrt(periods_per_year)

        # Sharpe ratio
        excess_return = annual_return - self.risk_free_rate
        sharpe = self.safe_divide(excess_return, annual_std, default=0)

        return sharpe

    def calculate_sortino_ratio(self, periods_per_year: int = 252) -> float:
        """
        Calculate Sortino ratio (uses downside deviation instead of total volatility).

        Args:
            periods_per_year: Number of trading periods per year

        Returns:
            Sortino ratio
        """
        if not self.returns or len(self.returns) < 2:
            return 0

        mean_return = sum(self.returns) / len(self.returns)

        # Calculate downside deviation
        downside_returns = [r for r in self.returns if r < 0]
        if not downside_returns:
            return 0

        downside_variance = sum(r ** 2 for r in downside_returns) / len(downside_returns)
        downside_dev = math.sqrt(downside_variance) if downside_variance > 0 else 0

        if downside_dev == 0:
            return 0

        # Annualize
        annual_return = mean_return * periods_per_year
        annual_downside_dev = downside_dev * math.sqrt(periods_per_year)

        # Sortino ratio
        excess_return = annual_return - self.risk_free_rate
        sortino = self.safe_divide(excess_return, annual_downside_dev, default=0)

        return sortino

    def calculate_max_drawdown(self) -> Dict[str, float]:
        """
        Calculate maximum drawdown from equity curve.

        Returns:
            Dictionary with max_drawdown, max_drawdown_pct, and recovery_periods
        """
        if not self.returns:
            return {'max_drawdown': 0, 'max_drawdown_pct': 0, 'drawdown_duration': 0}

        # Build equity curve
        equity_curve = [1.0]  # Start with $1
        for ret in self.returns:
            equity_curve.append(equity_curve[-1] * (1 + ret))

        # Calculate drawdowns
        max_equity = equity_curve[0]
        max_drawdown = 0
        max_drawdown_pct = 0
        current_drawdown_duration = 0
        max_drawdown_duration = 0

        for equity in equity_curve:
            if equity > max_equity:
                max_equity = equity
                current_drawdown_duration = 0
            else:
                drawdown = max_equity - equity
                drawdown_pct = self.safe_divide(drawdown, max_equity)

                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    max_drawdown_pct = drawdown_pct

                current_drawdown_duration += 1
                max_drawdown_duration = max(max_drawdown_duration, current_drawdown_duration)

        return {
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
            'drawdown_duration': max_drawdown_duration
        }

    def calculate_expectancy(self) -> float:
        """
        Calculate trade expectancy (average expected profit per trade).

        Returns:
            Expectancy value
        """
        if not self.pnl_values:
            return 0

        return sum(self.pnl_values) / len(self.pnl_values)

    def calculate_all_metrics(self) -> Dict[str, Any]:
        """
        Calculate all performance metrics.

        Returns:
            Dictionary with comprehensive performance analysis
        """
        basic_metrics = self.calculate_basic_metrics()

        self.metrics = {
            **basic_metrics,
            'profit_factor': self.calculate_profit_factor(),
            'sharpe_ratio': self.calculate_sharpe_ratio(),
            'sortino_ratio': self.calculate_sortino_ratio(),
            'expectancy': self.calculate_expectancy(),
            **self.calculate_max_drawdown()
        }

        return self.metrics

    def generate_interpretation(self) -> List[str]:
        """
        Generate human-readable interpretation of metrics.

        Returns:
            List of interpretation strings
        """
        if not self.metrics:
            self.calculate_all_metrics()

        interpretations = []

        # Win rate interpretation
        win_rate = self.metrics.get('win_rate', 0)
        if win_rate > 0.6:
            interpretations.append(f"Strong win rate of {win_rate:.1%} indicates consistent winning trades")
        elif win_rate > 0.5:
            interpretations.append(f"Positive win rate of {win_rate:.1%} shows more wins than losses")
        else:
            interpretations.append(f"Win rate of {win_rate:.1%} is below 50%, strategy depends on large winners")

        # Profit factor interpretation
        profit_factor = self.metrics.get('profit_factor', 0)
        if profit_factor > 2.0:
            interpretations.append(f"Excellent profit factor of {profit_factor:.2f} (profits are {profit_factor}x losses)")
        elif profit_factor > 1.5:
            interpretations.append(f"Good profit factor of {profit_factor:.2f} indicates healthy profitability")
        elif profit_factor > 1.0:
            interpretations.append(f"Profit factor of {profit_factor:.2f} is profitable but could be improved")
        else:
            interpretations.append(f"Profit factor of {profit_factor:.2f} indicates overall losses")

        # Sharpe ratio interpretation
        sharpe = self.metrics.get('sharpe_ratio', 0)
        if sharpe > 2.0:
            interpretations.append(f"Exceptional Sharpe ratio of {sharpe:.2f} shows excellent risk-adjusted returns")
        elif sharpe > 1.0:
            interpretations.append(f"Good Sharpe ratio of {sharpe:.2f} indicates favorable risk-adjusted performance")
        elif sharpe > 0:
            interpretations.append(f"Sharpe ratio of {sharpe:.2f} is positive but below optimal threshold")
        else:
            interpretations.append(f"Negative Sharpe ratio of {sharpe:.2f} indicates poor risk-adjusted returns")

        # Max drawdown interpretation
        max_dd_pct = self.metrics.get('max_drawdown_pct', 0)
        if max_dd_pct < 0.1:
            interpretations.append(f"Low maximum drawdown of {max_dd_pct:.1%} shows good risk control")
        elif max_dd_pct < 0.2:
            interpretations.append(f"Moderate maximum drawdown of {max_dd_pct:.1%} is acceptable for most strategies")
        else:
            interpretations.append(f"High maximum drawdown of {max_dd_pct:.1%} requires improved risk management")

        return interpretations

    def to_dict(self) -> Dict[str, Any]:
        """Export analysis results as dictionary."""
        if not self.metrics:
            self.calculate_all_metrics()

        return {
            'metrics': self.metrics,
            'interpretations': self.generate_interpretation(),
            'summary': f"Analyzed {self.metrics.get('total_trades', 0)} trades with {self.metrics.get('win_rate', 0):.1%} win rate and Sharpe ratio of {self.metrics.get('sharpe_ratio', 0):.2f}"
        }


def analyze_trades(trades_data: List[Dict[str, Any]], risk_free_rate: float = 0.02) -> Dict[str, Any]:
    """
    Convenience function to analyze trades.

    Args:
        trades_data: List of trade dictionaries
        risk_free_rate: Annual risk-free rate (default: 2%)

    Returns:
        Dictionary with analysis results
    """
    analyzer = TradeAnalyzer(trades_data, risk_free_rate)
    return analyzer.to_dict()
