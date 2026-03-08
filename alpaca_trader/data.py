import logging
from datetime import datetime, timedelta

import pandas as pd
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from alpaca_trader.client import AlpacaClient, is_crypto_symbol

logger = logging.getLogger("alpaca_trader")


TIMEFRAME_MAP = {
    "1Min": TimeFrame.Minute,
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame.Hour,
    "1Day": TimeFrame.Day,
}


def _extract_symbol_bars(bars_df, symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Pull each symbol's rows out of a multi-index (symbol, timestamp) DataFrame."""
    result = {}
    for symbol in symbols:
        try:
            symbol_df = bars_df.loc[symbol].copy()
            symbol_df.index = pd.to_datetime(symbol_df.index)
            result[symbol] = symbol_df.sort_index()
            logger.debug("%s: %d bars fetched", symbol, len(symbol_df))
        except KeyError:
            logger.warning("No data returned for %s", symbol)
    return result


def fetch_bars(
    client: AlpacaClient,
    symbols: list[str],
    timeframe: str,
    lookback_days: int,
) -> dict[str, pd.DataFrame]:
    """
    Fetch historical OHLCV bars for a list of symbols (stocks and/or crypto).

    Automatically routes crypto symbols (e.g. BTC/USD) to the crypto data
    client and stock symbols to the stock data client.

    Returns a dict mapping symbol -> DataFrame with columns:
    open, high, low, close, volume (indexed by timestamp).
    """
    tf = TIMEFRAME_MAP.get(timeframe)
    if tf is None:
        raise ValueError(
            f"Unknown timeframe '{timeframe}'. "
            f"Valid options: {list(TIMEFRAME_MAP.keys())}"
        )

    start = datetime.now() - timedelta(days=lookback_days)
    stock_symbols = [s for s in symbols if not is_crypto_symbol(s)]
    crypto_symbols = [s for s in symbols if is_crypto_symbol(s)]

    logger.info(
        "Fetching %s bars — %d stock(s), %d crypto (lookback=%d days)",
        timeframe,
        len(stock_symbols),
        len(crypto_symbols),
        lookback_days,
    )

    result = {}

    if stock_symbols:
        request = StockBarsRequest(
            symbol_or_symbols=stock_symbols,
            timeframe=tf,
            start=start,
        )
        bars = client.data.get_stock_bars(request)
        result.update(_extract_symbol_bars(bars.df, stock_symbols))

    if crypto_symbols:
        request = CryptoBarsRequest(
            symbol_or_symbols=crypto_symbols,
            timeframe=tf,
            start=start,
        )
        bars = client.crypto_data.get_crypto_bars(request)
        result.update(_extract_symbol_bars(bars.df, crypto_symbols))

    return result
