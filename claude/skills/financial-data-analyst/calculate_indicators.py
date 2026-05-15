"""
Technical Indicators Calculation Module

Calculates technical indicators from OHLCV data including RSI, MACD,
Bollinger Bands, moving averages, and generates trading signals.
"""

from typing import Dict, List, Any, Optional, Tuple
import math


class IndicatorCalculator:
    """Calculate technical indicators from OHLCV data."""

    def __init__(self, ohlcv_data: List[Dict[str, Any]]):
        """
        Initialize with OHLCV data.

        Args:
            ohlcv_data: List of dictionaries with fields:
                - timestamp/date: Time period
                - open: Opening price
                - high: High price
                - low: Low price
                - close: Closing price
                - volume: Trading volume
        """
        self.data = sorted(ohlcv_data, key=lambda x: x.get('timestamp', x.get('date', '')))
        self.closes = [float(d.get('close', 0)) for d in self.data]
        self.highs = [float(d.get('high', 0)) for d in self.data]
        self.lows = [float(d.get('low', 0)) for d in self.data]
        self.volumes = [float(d.get('volume', 0)) for d in self.data]
        self.indicators = {}

    def calculate_sma(self, period: int = 20) -> List[Optional[float]]:
        """
        Calculate Simple Moving Average.

        Args:
            period: Lookback period (default: 20)

        Returns:
            List of SMA values (None for insufficient data points)
        """
        sma = []
        for i in range(len(self.closes)):
            if i < period - 1:
                sma.append(None)
            else:
                avg = sum(self.closes[i - period + 1:i + 1]) / period
                sma.append(avg)
        return sma

    def calculate_ema(self, period: int = 20) -> List[Optional[float]]:
        """
        Calculate Exponential Moving Average.

        Args:
            period: Lookback period (default: 20)

        Returns:
            List of EMA values
        """
        if len(self.closes) < period:
            return [None] * len(self.closes)

        multiplier = 2 / (period + 1)
        ema = []

        # Start with SMA
        sma = sum(self.closes[:period]) / period
        ema.extend([None] * (period - 1))
        ema.append(sma)

        # Calculate EMA
        for i in range(period, len(self.closes)):
            ema_value = (self.closes[i] - ema[-1]) * multiplier + ema[-1]
            ema.append(ema_value)

        return ema

    def calculate_rsi(self, period: int = 14) -> List[Optional[float]]:
        """
        Calculate Relative Strength Index.

        Args:
            period: Lookback period (default: 14)

        Returns:
            List of RSI values (0-100)
        """
        if len(self.closes) < period + 1:
            return [None] * len(self.closes)

        rsi = [None] * period

        # Calculate initial gains and losses
        gains = []
        losses = []

        for i in range(1, len(self.closes)):
            change = self.closes[i] - self.closes[i - 1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))

        # Initial average gain and loss
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Calculate first RSI
        if avg_loss == 0:
            rsi.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - (100 / (1 + rs)))

        # Calculate remaining RSI values using smoothed averages
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

            if avg_loss == 0:
                rsi.append(100)
            else:
                rs = avg_gain / avg_loss
                rsi.append(100 - (100 / (1 + rs)))

        return rsi

    def calculate_macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, List[Optional[float]]]:
        """
        Calculate MACD (Moving Average Convergence Divergence).

        Args:
            fast: Fast EMA period (default: 12)
            slow: Slow EMA period (default: 26)
            signal: Signal line period (default: 9)

        Returns:
            Dictionary with macd_line, signal_line, and histogram
        """
        fast_ema = self.calculate_ema(fast)
        slow_ema = self.calculate_ema(slow)

        # Calculate MACD line
        macd_line = []
        for i in range(len(self.closes)):
            if fast_ema[i] is None or slow_ema[i] is None:
                macd_line.append(None)
            else:
                macd_line.append(fast_ema[i] - slow_ema[i])

        # Calculate signal line (EMA of MACD)
        signal_line = [None] * (slow - 1 + signal - 1)
        valid_macd = [m for m in macd_line if m is not None]

        if len(valid_macd) >= signal:
            # Initial signal (SMA of MACD)
            signal_sma = sum(valid_macd[:signal]) / signal
            signal_line.append(signal_sma)

            # EMA of MACD for signal line
            multiplier = 2 / (signal + 1)
            for i in range(signal, len(valid_macd)):
                sig_value = (valid_macd[i] - signal_line[-1]) * multiplier + signal_line[-1]
                signal_line.append(sig_value)

        # Pad signal line to match length
        while len(signal_line) < len(macd_line):
            signal_line.append(None)

        # Calculate histogram
        histogram = []
        for i in range(len(macd_line)):
            if macd_line[i] is None or signal_line[i] is None:
                histogram.append(None)
            else:
                histogram.append(macd_line[i] - signal_line[i])

        return {
            'macd_line': macd_line,
            'signal_line': signal_line,
            'histogram': histogram
        }

    def calculate_bollinger_bands(self, period: int = 20, num_std: float = 2.0) -> Dict[str, List[Optional[float]]]:
        """
        Calculate Bollinger Bands.

        Args:
            period: SMA period (default: 20)
            num_std: Number of standard deviations (default: 2.0)

        Returns:
            Dictionary with upper, middle, and lower bands
        """
        middle_band = self.calculate_sma(period)

        upper_band = []
        lower_band = []

        for i in range(len(self.closes)):
            if i < period - 1 or middle_band[i] is None:
                upper_band.append(None)
                lower_band.append(None)
            else:
                # Calculate standard deviation
                data_slice = self.closes[i - period + 1:i + 1]
                mean = middle_band[i]
                variance = sum((x - mean) ** 2 for x in data_slice) / period
                std_dev = math.sqrt(variance)

                upper_band.append(mean + num_std * std_dev)
                lower_band.append(mean - num_std * std_dev)

        return {
            'upper': upper_band,
            'middle': middle_band,
            'lower': lower_band
        }

    def calculate_atr(self, period: int = 14) -> List[Optional[float]]:
        """
        Calculate Average True Range.

        Args:
            period: Lookback period (default: 14)

        Returns:
            List of ATR values
        """
        if len(self.closes) < period + 1:
            return [None] * len(self.closes)

        true_ranges = []

        for i in range(1, len(self.closes)):
            high_low = self.highs[i] - self.lows[i]
            high_close = abs(self.highs[i] - self.closes[i - 1])
            low_close = abs(self.lows[i] - self.closes[i - 1])
            true_range = max(high_low, high_close, low_close)
            true_ranges.append(true_range)

        atr = [None]  # First value has no previous close

        # Initial ATR (SMA of true ranges)
        initial_atr = sum(true_ranges[:period]) / period
        atr.extend([None] * (period - 1))
        atr.append(initial_atr)

        # Smoothed ATR
        for i in range(period, len(true_ranges)):
            smoothed_atr = (atr[-1] * (period - 1) + true_ranges[i]) / period
            atr.append(smoothed_atr)

        return atr

    def calculate_stochastic(self, k_period: int = 14, d_period: int = 3) -> Dict[str, List[Optional[float]]]:
        """
        Calculate Stochastic Oscillator.

        Args:
            k_period: %K period (default: 14)
            d_period: %D period (default: 3)

        Returns:
            Dictionary with %K and %D lines
        """
        k_values = []

        for i in range(len(self.closes)):
            if i < k_period - 1:
                k_values.append(None)
            else:
                period_high = max(self.highs[i - k_period + 1:i + 1])
                period_low = min(self.lows[i - k_period + 1:i + 1])
                current_close = self.closes[i]

                if period_high == period_low:
                    k_values.append(50)  # Neutral when no range
                else:
                    k = 100 * (current_close - period_low) / (period_high - period_low)
                    k_values.append(k)

        # Calculate %D (SMA of %K)
        d_values = []
        for i in range(len(k_values)):
            if i < k_period - 1 + d_period - 1 or k_values[i] is None:
                d_values.append(None)
            else:
                valid_k = [k for k in k_values[i - d_period + 1:i + 1] if k is not None]
                if valid_k:
                    d_values.append(sum(valid_k) / len(valid_k))
                else:
                    d_values.append(None)

        return {
            'k': k_values,
            'd': d_values
        }

    def generate_signals(self) -> Dict[str, Any]:
        """
        Generate trading signals based on calculated indicators.

        Returns:
            Dictionary with signal interpretations
        """
        signals = {}

        # RSI signals
        rsi = self.calculate_rsi()
        if rsi[-1] is not None:
            if rsi[-1] > 70:
                signals['rsi_signal'] = 'Overbought - Consider selling'
            elif rsi[-1] < 30:
                signals['rsi_signal'] = 'Oversold - Consider buying'
            else:
                signals['rsi_signal'] = 'Neutral'
            signals['rsi_value'] = rsi[-1]

        # MACD signals
        macd = self.calculate_macd()
        if macd['macd_line'][-1] is not None and macd['signal_line'][-1] is not None:
            if macd['macd_line'][-1] > macd['signal_line'][-1]:
                signals['macd_signal'] = 'Bullish - MACD above signal'
            else:
                signals['macd_signal'] = 'Bearish - MACD below signal'
            signals['macd_histogram'] = macd['histogram'][-1]

        # Bollinger Bands signals
        bb = self.calculate_bollinger_bands()
        if bb['upper'][-1] is not None and bb['lower'][-1] is not None:
            current_price = self.closes[-1]
            if current_price > bb['upper'][-1]:
                signals['bb_signal'] = 'Overbought - Price above upper band'
            elif current_price < bb['lower'][-1]:
                signals['bb_signal'] = 'Oversold - Price below lower band'
            else:
                signals['bb_signal'] = 'Within bands - Normal range'

        # Moving average signals
        sma_20 = self.calculate_sma(20)
        sma_50 = self.calculate_sma(50)
        if sma_20[-1] is not None and sma_50[-1] is not None:
            if sma_20[-1] > sma_50[-1]:
                signals['ma_signal'] = 'Bullish - Short MA above long MA'
            else:
                signals['ma_signal'] = 'Bearish - Short MA below long MA'

        return signals

    def calculate_all_indicators(self) -> Dict[str, Any]:
        """
        Calculate all technical indicators.

        Returns:
            Dictionary with all indicator values
        """
        self.indicators = {
            'sma_20': self.calculate_sma(20),
            'sma_50': self.calculate_sma(50),
            'sma_200': self.calculate_sma(200),
            'ema_12': self.calculate_ema(12),
            'ema_26': self.calculate_ema(26),
            'rsi_14': self.calculate_rsi(14),
            'macd': self.calculate_macd(),
            'bollinger_bands': self.calculate_bollinger_bands(),
            'atr_14': self.calculate_atr(14),
            'stochastic': self.calculate_stochastic(),
            'signals': self.generate_signals()
        }

        return self.indicators

    def to_dict(self) -> Dict[str, Any]:
        """Export indicator calculations as dictionary."""
        if not self.indicators:
            self.calculate_all_indicators()

        # Get latest values for summary
        latest_values = {}
        for key, value in self.indicators.items():
            if key == 'signals':
                latest_values['signals'] = value
            elif isinstance(value, dict):
                latest_values[key] = {k: v[-1] if isinstance(v, list) and v else v for k, v in value.items()}
            elif isinstance(value, list):
                latest_values[key] = value[-1] if value else None

        return {
            'indicators': self.indicators,
            'latest_values': latest_values,
            'summary': f"Calculated {len([k for k in self.indicators.keys() if k != 'signals'])} technical indicators for {len(self.data)} periods"
        }


def calculate_indicators(ohlcv_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convenience function to calculate technical indicators.

    Args:
        ohlcv_data: List of OHLCV dictionaries

    Returns:
        Dictionary with indicator calculations
    """
    calculator = IndicatorCalculator(ohlcv_data)
    return calculator.to_dict()
