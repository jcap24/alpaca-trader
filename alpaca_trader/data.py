import logging
from datetime import datetime, timedelta

import pandas as pd
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from alpaca_trader.client import AlpacaClient

logger = logging.getLogger("alpaca_trader")

TIMEFRAME_MAP = {
    "1Min": TimeFrame.Minute,
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame.Hour,
    "1Day": TimeFrame.Day,
}


def fetch_bars(
    client: AlpacaClient,
    symbols: list[str],
    timeframe: str,
    lookback_days: int,
) -> dict[str, pd.DataFrame]:
    """
    Fetch historical OHLCV bars for a list of symbols.

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

    logger.info(
        "Fetching %s bars for %d symbols (lookback=%d days)",
        timeframe,
        len(symbols),
        lookback_days,
    )

    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=tf,
        start=start,
    )
    bars = client.data.get_stock_bars(request)
    df = bars.df  # Multi-index: (symbol, timestamp)

    result = {}
    for symbol in symbols:
        try:
            symbol_df = df.loc[symbol].copy()
            symbol_df.index = pd.to_datetime(symbol_df.index)
            symbol_df = symbol_df.sort_index()
            result[symbol] = symbol_df
            logger.debug("%s: %d bars fetched", symbol, len(symbol_df))
        except KeyError:
            logger.warning("No data returned for %s", symbol)

    return result
