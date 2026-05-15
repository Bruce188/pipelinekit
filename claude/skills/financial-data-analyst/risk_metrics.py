"""
Risk Metrics Calculation Module

Computes risk metrics including VaR, CVaR, volatility, beta, downside deviation,
and risk-adjusted performance measures.
"""

from typing import Dict, List, Any, Optional, Tuple
import math


class RiskAnalyzer:
    """Calculate risk metrics from returns data."""

    def __init__(self, returns_data: List[float], benchmark_returns: Optional[List[float]] = None,
                 risk_free_rate: float = 0.02):
        """
        Initialize with returns data.

        Args:
            returns_data: List of periodic returns (e.g., daily, weekly)
            benchmark_returns: List of benchmark returns for beta calculation (optional)
            risk_free_rate: Annual risk-free rate (default: 2%)
        """
        self.returns = returns_data
        self.benchmark_returns = benchmark_returns
        self.risk_free_rate = risk_free_rate
        self.metrics = {}

    def safe_divide(self, numerator: float, denominator: float, default: float = 0.0) -> float:
        """Safely divide two numbers, returning default if denominator is zero."""
        if denominator == 0 or math.isnan(denominator) or math.isinf(denominator):
            return default
        result = numerator / denominator
        return result if not (math.isnan(result) or math.isinf(result)) else default

    def calculate_volatility(self, periods_per_year: int = 252) -> Dict[str, float]:
        """
        Calculate historical volatility.

        Args:
            periods_per_year: Number of periods per year for annualization

        Returns:
            Dictionary with period and annualized volatility
        """
        if len(self.returns) < 2:
            return {'period_volatility': 0, 'annual_volatility': 0}

        mean_return = sum(self.returns) / len(self.returns)
        variance = sum((r - mean_return) ** 2 for r in self.returns) / (len(self.returns) - 1)
        period_vol = math.sqrt(variance) if variance > 0 else 0
        annual_vol = period_vol * math.sqrt(periods_per_year)

        return {
            'period_volatility': period_vol,
            'annual_volatility': annual_vol
        }

    def calculate_downside_deviation(self, target_return: float = 0, periods_per_year: int = 252) -> Dict[str, float]:
        """
        Calculate downside deviation (volatility of returns below target).

        Args:
            target_return: Target/minimum acceptable return (default: 0)
            periods_per_year: Number of periods per year for annualization

        Returns:
            Dictionary with downside deviation metrics
        """
        downside_returns = [min(r - target_return, 0) for r in self.returns]
        downside_variance = sum(r ** 2 for r in downside_returns) / len(downside_returns)
        period_dd = math.sqrt(downside_variance) if downside_variance > 0 else 0
        annual_dd = period_dd * math.sqrt(periods_per_year)

        return {
            'period_downside_deviation': period_dd,
            'annual_downside_deviation': annual_dd
        }

    def calculate_var(self, confidence_level: float = 0.95) -> Dict[str, float]:
        """
        Calculate Value at Risk (VaR) using historical simulation.

        Args:
            confidence_level: Confidence level (default: 0.95 for 95% VaR)

        Returns:
            Dictionary with VaR at different confidence levels
        """
        if not self.returns:
            return {'var_95': 0, 'var_99': 0}

        sorted_returns = sorted(self.returns)
        n = len(sorted_returns)

        # 95% VaR
        var_95_index = int((1 - 0.95) * n)
        var_95 = sorted_returns[var_95_index] if var_95_index < n else sorted_returns[0]

        # 99% VaR
        var_99_index = int((1 - 0.99) * n)
        var_99 = sorted_returns[var_99_index] if var_99_index < n else sorted_returns[0]

        return {
            'var_95': abs(var_95),  # Report as positive loss
            'var_99': abs(var_99),
            'interpretation': f"95% VaR: {abs(var_95):.2%} - Expected loss not exceeded in 95% of cases"
        }

    def calculate_cvar(self, confidence_level: float = 0.95) -> Dict[str, float]:
        """
        Calculate Conditional Value at Risk (CVaR/Expected Shortfall).
        Average of losses beyond VaR threshold.

        Args:
            confidence_level: Confidence level (default: 0.95)

        Returns:
            Dictionary with CVaR metrics
        """
        if not self.returns:
            return {'cvar_95': 0, 'cvar_99': 0}

        sorted_returns = sorted(self.returns)
        n = len(sorted_returns)

        # 95% CVaR
        var_95_index = int((1 - 0.95) * n)
        tail_95 = sorted_returns[:var_95_index + 1]
        cvar_95 = sum(tail_95) / len(tail_95) if tail_95 else 0

        # 99% CVaR
        var_99_index = int((1 - 0.99) * n)
        tail_99 = sorted_returns[:var_99_index + 1]
        cvar_99 = sum(tail_99) / len(tail_99) if tail_99 else 0

        return {
            'cvar_95': abs(cvar_95),
            'cvar_99': abs(cvar_99),
            'interpretation': f"95% CVaR: {abs(cvar_95):.2%} - Average loss in worst 5% of cases"
        }

    def calculate_beta(self) -> Dict[str, Any]:
        """
        Calculate beta (systematic risk relative to benchmark).

        Returns:
            Dictionary with beta and related metrics
        """
        if not self.benchmark_returns or len(self.returns) != len(self.benchmark_returns):
            return {
                'beta': None,
                'interpretation': 'Benchmark returns required for beta calculation'
            }

        # Calculate means
        mean_return = sum(self.returns) / len(self.returns)
        mean_benchmark = sum(self.benchmark_returns) / len(self.benchmark_returns)

        # Calculate covariance and variance
        covariance = sum((self.returns[i] - mean_return) * (self.benchmark_returns[i] - mean_benchmark)
                        for i in range(len(self.returns))) / (len(self.returns) - 1)

        benchmark_variance = sum((r - mean_benchmark) ** 2 for r in self.benchmark_returns) / (len(self.benchmark_returns) - 1)

        beta = self.safe_divide(covariance, benchmark_variance, default=1.0)

        # Calculate correlation
        returns_std = math.sqrt(sum((r - mean_return) ** 2 for r in self.returns) / (len(self.returns) - 1))
        benchmark_std = math.sqrt(benchmark_variance)
        correlation = self.safe_divide(covariance, (returns_std * benchmark_std), default=0)

        interpretation = []
        if beta > 1.2:
            interpretation.append(f"High beta of {beta:.2f} indicates significantly more volatile than benchmark")
        elif beta > 1.0:
            interpretation.append(f"Beta of {beta:.2f} indicates slightly more volatile than benchmark")
        elif beta > 0.8:
            interpretation.append(f"Beta of {beta:.2f} indicates slightly less volatile than benchmark")
        else:
            interpretation.append(f"Low beta of {beta:.2f} indicates much less volatile than benchmark")

        return {
            'beta': beta,
            'correlation': correlation,
            'interpretation': ' | '.join(interpretation)
        }

    def calculate_sharpe_ratio(self, periods_per_year: int = 252) -> float:
        """
        Calculate Sharpe ratio.

        Args:
            periods_per_year: Number of periods per year

        Returns:
            Sharpe ratio
        """
        if len(self.returns) < 2:
            return 0

        mean_return = sum(self.returns) / len(self.returns)
        vol = self.calculate_volatility(periods_per_year)['annual_volatility']

        annual_return = mean_return * periods_per_year
        excess_return = annual_return - self.risk_free_rate

        return self.safe_divide(excess_return, vol, default=0)

    def calculate_sortino_ratio(self, periods_per_year: int = 252) -> float:
        """
        Calculate Sortino ratio.

        Args:
            periods_per_year: Number of periods per year

        Returns:
            Sortino ratio
        """
        if len(self.returns) < 2:
            return 0

        mean_return = sum(self.returns) / len(self.returns)
        downside_dev = self.calculate_downside_deviation(0, periods_per_year)['annual_downside_deviation']

        annual_return = mean_return * periods_per_year
        excess_return = annual_return - self.risk_free_rate

        return self.safe_divide(excess_return, downside_dev, default=0)

    def calculate_calmar_ratio(self, max_drawdown: float, periods_per_year: int = 252) -> float:
        """
        Calculate Calmar ratio (return / max drawdown).

        Args:
            max_drawdown: Maximum drawdown as decimal (e.g., 0.20 for 20%)
            periods_per_year: Number of periods per year

        Returns:
            Calmar ratio
        """
        if max_drawdown == 0:
            return 0

        mean_return = sum(self.returns) / len(self.returns) if self.returns else 0
        annual_return = mean_return * periods_per_year

        return self.safe_divide(annual_return, max_drawdown, default=0)

    def calculate_information_ratio(self) -> Dict[str, Any]:
        """
        Calculate Information ratio (excess return / tracking error).

        Returns:
            Dictionary with information ratio and tracking error
        """
        if not self.benchmark_returns or len(self.returns) != len(self.benchmark_returns):
            return {
                'information_ratio': None,
                'tracking_error': None,
                'interpretation': 'Benchmark returns required'
            }

        # Calculate excess returns
        excess_returns = [self.returns[i] - self.benchmark_returns[i] for i in range(len(self.returns))]

        # Tracking error (std dev of excess returns)
        mean_excess = sum(excess_returns) / len(excess_returns)
        tracking_variance = sum((r - mean_excess) ** 2 for r in excess_returns) / (len(excess_returns) - 1)
        tracking_error = math.sqrt(tracking_variance) if tracking_variance > 0 else 0

        # Information ratio
        information_ratio = self.safe_divide(mean_excess, tracking_error, default=0)

        return {
            'information_ratio': information_ratio,
            'tracking_error': tracking_error,
            'average_excess_return': mean_excess,
            'interpretation': f"IR of {information_ratio:.2f} with {tracking_error:.2%} tracking error"
        }

    def calculate_all_metrics(self, max_drawdown: Optional[float] = None) -> Dict[str, Any]:
        """
        Calculate all risk metrics.

        Args:
            max_drawdown: Optional max drawdown for Calmar ratio

        Returns:
            Dictionary with comprehensive risk analysis
        """
        self.metrics = {
            'volatility': self.calculate_volatility(),
            'downside_deviation': self.calculate_downside_deviation(),
            'var': self.calculate_var(),
            'cvar': self.calculate_cvar(),
            'beta': self.calculate_beta(),
            'sharpe_ratio': self.calculate_sharpe_ratio(),
            'sortino_ratio': self.calculate_sortino_ratio(),
            'information_ratio': self.calculate_information_ratio()
        }

        if max_drawdown is not None:
            self.metrics['calmar_ratio'] = self.calculate_calmar_ratio(max_drawdown)

        return self.metrics

    def generate_interpretation(self) -> List[str]:
        """
        Generate human-readable interpretation of risk metrics.

        Returns:
            List of interpretation strings
        """
        if not self.metrics:
            self.calculate_all_metrics()

        interpretations = []

        # Volatility interpretation
        vol = self.metrics.get('volatility', {})
        annual_vol = vol.get('annual_volatility', 0)
        if annual_vol > 0.4:
            interpretations.append(f"High annual volatility of {annual_vol:.1%} indicates significant price fluctuations")
        elif annual_vol > 0.2:
            interpretations.append(f"Moderate annual volatility of {annual_vol:.1%} is typical for equity investments")
        else:
            interpretations.append(f"Low annual volatility of {annual_vol:.1%} suggests stable returns")

        # VaR interpretation
        var_metrics = self.metrics.get('var', {})
        interpretations.append(var_metrics.get('interpretation', ''))

        # Beta interpretation
        beta_metrics = self.metrics.get('beta', {})
        if beta_metrics.get('beta') is not None:
            interpretations.append(beta_metrics.get('interpretation', ''))

        # Sharpe ratio interpretation
        sharpe = self.metrics.get('sharpe_ratio', 0)
        if sharpe > 2.0:
            interpretations.append(f"Excellent Sharpe ratio of {sharpe:.2f} shows strong risk-adjusted returns")
        elif sharpe > 1.0:
            interpretations.append(f"Good Sharpe ratio of {sharpe:.2f} indicates favorable risk-adjusted performance")
        elif sharpe > 0:
            interpretations.append(f"Positive Sharpe ratio of {sharpe:.2f} but room for improvement")
        else:
            interpretations.append(f"Negative Sharpe ratio of {sharpe:.2f} indicates returns don't compensate for risk")

        return interpretations

    def to_dict(self) -> Dict[str, Any]:
        """Export risk analysis as dictionary."""
        if not self.metrics:
            self.calculate_all_metrics()

        return {
            'metrics': self.metrics,
            'interpretations': self.generate_interpretation(),
            'summary': f"Risk analysis based on {len(self.returns)} return periods with {self.metrics.get('volatility', {}).get('annual_volatility', 0):.1%} annual volatility"
        }


def analyze_risk(returns_data: List[float], benchmark_returns: Optional[List[float]] = None,
                risk_free_rate: float = 0.02, max_drawdown: Optional[float] = None) -> Dict[str, Any]:
    """
    Convenience function to analyze risk.

    Args:
        returns_data: List of periodic returns
        benchmark_returns: Optional benchmark returns
        risk_free_rate: Annual risk-free rate (default: 2%)
        max_drawdown: Optional max drawdown for Calmar ratio

    Returns:
        Dictionary with risk analysis results
    """
    analyzer = RiskAnalyzer(returns_data, benchmark_returns, risk_free_rate)
    analyzer.calculate_all_metrics(max_drawdown)
    return analyzer.to_dict()
