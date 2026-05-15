"""
Portfolio Analysis Module

Analyzes portfolio composition with correlation matrices, diversification metrics,
optimal weights, and concentration risk analysis.
"""

from typing import Dict, List, Any, Optional, Tuple
import math


class PortfolioAnalyzer:
    """Analyze portfolio composition and calculate diversification metrics."""

    def __init__(self, assets_returns: Dict[str, List[float]], weights: Optional[Dict[str, float]] = None):
        """
        Initialize with asset returns data.

        Args:
            assets_returns: Dictionary mapping asset names to their return series
                Example: {'AAPL': [0.01, -0.02, 0.03], 'GOOGL': [0.02, 0.01, -0.01]}
            weights: Optional dictionary of asset weights (must sum to 1.0)
                Example: {'AAPL': 0.6, 'GOOGL': 0.4}
        """
        self.assets_returns = assets_returns
        self.asset_names = list(assets_returns.keys())
        self.n_assets = len(self.asset_names)

        # Use equal weights if not provided
        if weights is None:
            equal_weight = 1.0 / self.n_assets if self.n_assets > 0 else 0
            self.weights = {asset: equal_weight for asset in self.asset_names}
        else:
            self.weights = weights

        self.metrics = {}

    def safe_divide(self, numerator: float, denominator: float, default: float = 0.0) -> float:
        """Safely divide two numbers, returning default if denominator is zero."""
        if denominator == 0 or math.isnan(denominator) or math.isinf(denominator):
            return default
        result = numerator / denominator
        return result if not (math.isnan(result) or math.isinf(result)) else default

    def calculate_correlation_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Calculate correlation matrix between all assets.

        Returns:
            Nested dictionary representing correlation matrix
        """
        correlation_matrix = {}

        for asset1 in self.asset_names:
            correlation_matrix[asset1] = {}
            returns1 = self.assets_returns[asset1]
            mean1 = sum(returns1) / len(returns1)
            std1 = math.sqrt(sum((r - mean1) ** 2 for r in returns1) / (len(returns1) - 1))

            for asset2 in self.asset_names:
                returns2 = self.assets_returns[asset2]
                mean2 = sum(returns2) / len(returns2)
                std2 = math.sqrt(sum((r - mean2) ** 2 for r in returns2) / (len(returns2) - 1))

                if asset1 == asset2:
                    correlation_matrix[asset1][asset2] = 1.0
                else:
                    # Calculate covariance
                    covariance = sum((returns1[i] - mean1) * (returns2[i] - mean2)
                                   for i in range(len(returns1))) / (len(returns1) - 1)

                    # Calculate correlation
                    correlation = self.safe_divide(covariance, (std1 * std2), default=0)
                    correlation_matrix[asset1][asset2] = correlation

        return correlation_matrix

    def calculate_covariance_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Calculate covariance matrix between all assets.

        Returns:
            Nested dictionary representing covariance matrix
        """
        covariance_matrix = {}

        for asset1 in self.asset_names:
            covariance_matrix[asset1] = {}
            returns1 = self.assets_returns[asset1]
            mean1 = sum(returns1) / len(returns1)

            for asset2 in self.asset_names:
                returns2 = self.assets_returns[asset2]
                mean2 = sum(returns2) / len(returns2)

                # Calculate covariance
                covariance = sum((returns1[i] - mean1) * (returns2[i] - mean2)
                               for i in range(len(returns1))) / (len(returns1) - 1)

                covariance_matrix[asset1][asset2] = covariance

        return covariance_matrix

    def calculate_portfolio_variance(self) -> float:
        """
        Calculate portfolio variance based on weights and covariance matrix.

        Returns:
            Portfolio variance
        """
        covariance_matrix = self.calculate_covariance_matrix()

        variance = 0
        for asset1 in self.asset_names:
            for asset2 in self.asset_names:
                weight1 = self.weights.get(asset1, 0)
                weight2 = self.weights.get(asset2, 0)
                cov = covariance_matrix[asset1][asset2]
                variance += weight1 * weight2 * cov

        return variance

    def calculate_portfolio_std(self) -> float:
        """
        Calculate portfolio standard deviation (volatility).

        Returns:
            Portfolio standard deviation
        """
        variance = self.calculate_portfolio_variance()
        return math.sqrt(variance) if variance > 0 else 0

    def calculate_portfolio_return(self) -> float:
        """
        Calculate expected portfolio return based on historical returns and weights.

        Returns:
            Expected portfolio return
        """
        portfolio_return = 0

        for asset in self.asset_names:
            returns = self.assets_returns[asset]
            mean_return = sum(returns) / len(returns)
            weight = self.weights.get(asset, 0)
            portfolio_return += weight * mean_return

        return portfolio_return

    def calculate_diversification_ratio(self) -> float:
        """
        Calculate diversification ratio.
        Ratio of weighted average volatility to portfolio volatility.
        Higher is better (more diversification benefit).

        Returns:
            Diversification ratio
        """
        # Calculate individual asset volatilities
        weighted_vol_sum = 0

        for asset in self.asset_names:
            returns = self.assets_returns[asset]
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
            volatility = math.sqrt(variance) if variance > 0 else 0

            weight = self.weights.get(asset, 0)
            weighted_vol_sum += weight * volatility

        # Portfolio volatility
        portfolio_vol = self.calculate_portfolio_std()

        # Diversification ratio
        return self.safe_divide(weighted_vol_sum, portfolio_vol, default=1.0)

    def calculate_effective_number_assets(self) -> float:
        """
        Calculate effective number of assets (based on Herfindahl index).
        Measures how concentrated the portfolio is.

        Returns:
            Effective number of assets
        """
        sum_squared_weights = sum(w ** 2 for w in self.weights.values())
        return self.safe_divide(1.0, sum_squared_weights, default=1.0)

    def calculate_concentration_risk(self) -> Dict[str, Any]:
        """
        Calculate concentration risk metrics.

        Returns:
            Dictionary with concentration metrics
        """
        sorted_weights = sorted(self.weights.items(), key=lambda x: x[1], reverse=True)

        top_3_weight = sum(w for _, w in sorted_weights[:3])
        top_5_weight = sum(w for _, w in sorted_weights[:5])

        herfindahl_index = sum(w ** 2 for w in self.weights.values())

        return {
            'top_3_concentration': top_3_weight,
            'top_5_concentration': top_5_weight,
            'herfindahl_index': herfindahl_index,
            'effective_n_assets': self.calculate_effective_number_assets(),
            'interpretation': self._interpret_concentration(herfindahl_index, top_3_weight)
        }

    def _interpret_concentration(self, herfindahl: float, top_3: float) -> str:
        """Generate concentration interpretation."""
        if top_3 > 0.75:
            return f"High concentration: Top 3 assets represent {top_3:.1%} of portfolio"
        elif top_3 > 0.5:
            return f"Moderate concentration: Top 3 assets represent {top_3:.1%} of portfolio"
        else:
            return f"Well diversified: Top 3 assets represent only {top_3:.1%} of portfolio"

    def calculate_sharpe_optimal_weights(self, risk_free_rate: float = 0.02) -> Dict[str, float]:
        """
        Calculate optimal weights for maximum Sharpe ratio (simplified).
        Uses a basic mean-variance optimization approach.

        Args:
            risk_free_rate: Risk-free rate for Sharpe calculation

        Returns:
            Dictionary of optimal weights
        """
        # Calculate expected returns for each asset
        expected_returns = {}
        for asset in self.asset_names:
            returns = self.assets_returns[asset]
            expected_returns[asset] = sum(returns) / len(returns)

        # Calculate excess returns
        excess_returns = {asset: ret - risk_free_rate for asset, ret in expected_returns.items()}

        # Simplified optimization: weight proportional to excess return / variance
        # This is a basic heuristic, not true optimization
        scores = {}
        for asset in self.asset_names:
            returns = self.assets_returns[asset]
            mean_return = expected_returns[asset]
            variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
            volatility = math.sqrt(variance) if variance > 0 else 1

            # Score = excess return / volatility
            score = self.safe_divide(excess_returns[asset], volatility, default=0)
            scores[asset] = max(score, 0)  # No negative weights

        # Normalize to sum to 1.0
        total_score = sum(scores.values())
        if total_score > 0:
            optimal_weights = {asset: score / total_score for asset, score in scores.items()}
        else:
            # Equal weights if all scores are zero
            equal_weight = 1.0 / self.n_assets
            optimal_weights = {asset: equal_weight for asset in self.asset_names}

        return optimal_weights

    def calculate_minimum_variance_weights(self) -> Dict[str, float]:
        """
        Calculate weights for minimum variance portfolio (simplified).

        Returns:
            Dictionary of minimum variance weights
        """
        # Calculate inverse volatilities
        inv_volatilities = {}

        for asset in self.asset_names:
            returns = self.assets_returns[asset]
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
            volatility = math.sqrt(variance) if variance > 0 else 1

            inv_volatilities[asset] = self.safe_divide(1.0, volatility, default=0)

        # Normalize to sum to 1.0
        total_inv_vol = sum(inv_volatilities.values())
        if total_inv_vol > 0:
            min_var_weights = {asset: inv_vol / total_inv_vol for asset, inv_vol in inv_volatilities.items()}
        else:
            equal_weight = 1.0 / self.n_assets
            min_var_weights = {asset: equal_weight for asset in self.asset_names}

        return min_var_weights

    def calculate_all_metrics(self) -> Dict[str, Any]:
        """
        Calculate all portfolio metrics.

        Returns:
            Dictionary with comprehensive portfolio analysis
        """
        self.metrics = {
            'correlation_matrix': self.calculate_correlation_matrix(),
            'current_weights': self.weights,
            'portfolio_return': self.calculate_portfolio_return(),
            'portfolio_volatility': self.calculate_portfolio_std(),
            'portfolio_variance': self.calculate_portfolio_variance(),
            'diversification_ratio': self.calculate_diversification_ratio(),
            'concentration_risk': self.calculate_concentration_risk(),
            'optimal_weights_sharpe': self.calculate_sharpe_optimal_weights(),
            'optimal_weights_min_variance': self.calculate_minimum_variance_weights()
        }

        return self.metrics

    def generate_interpretation(self) -> List[str]:
        """
        Generate human-readable interpretation of portfolio metrics.

        Returns:
            List of interpretation strings
        """
        if not self.metrics:
            self.calculate_all_metrics()

        interpretations = []

        # Diversification interpretation
        div_ratio = self.metrics.get('diversification_ratio', 1.0)
        if div_ratio > 1.5:
            interpretations.append(f"Excellent diversification ratio of {div_ratio:.2f} shows strong diversification benefit")
        elif div_ratio > 1.2:
            interpretations.append(f"Good diversification ratio of {div_ratio:.2f} indicates moderate diversification")
        else:
            interpretations.append(f"Low diversification ratio of {div_ratio:.2f} suggests limited diversification benefit")

        # Concentration interpretation
        concentration = self.metrics.get('concentration_risk', {})
        interpretations.append(concentration.get('interpretation', ''))

        # Effective number of assets
        eff_n = concentration.get('effective_n_assets', 0)
        interpretations.append(f"Effective number of assets: {eff_n:.1f} out of {self.n_assets} total assets")

        # Portfolio metrics
        port_return = self.metrics.get('portfolio_return', 0)
        port_vol = self.metrics.get('portfolio_volatility', 0)
        interpretations.append(f"Portfolio: {port_return:.2%} return with {port_vol:.2%} volatility")

        return interpretations

    def to_dict(self) -> Dict[str, Any]:
        """Export portfolio analysis as dictionary."""
        if not self.metrics:
            self.calculate_all_metrics()

        return {
            'metrics': self.metrics,
            'interpretations': self.generate_interpretation(),
            'summary': f"Portfolio analysis for {self.n_assets} assets with {self.metrics.get('diversification_ratio', 0):.2f} diversification ratio"
        }


def analyze_portfolio(assets_returns: Dict[str, List[float]],
                     weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """
    Convenience function to analyze portfolio.

    Args:
        assets_returns: Dictionary mapping asset names to return series
        weights: Optional dictionary of asset weights

    Returns:
        Dictionary with portfolio analysis results
    """
    analyzer = PortfolioAnalyzer(assets_returns, weights)
    return analyzer.to_dict()
