# services/market_service.py
from typing import Optional, Dict, Any, List
import math
import logging

from core.connection_manager import manager as connection_manager

logger = logging.getLogger("bridge")


def get_market(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Return market tick and symbol info for the requested symbol.

    Defensive: returns None when no data is available or on error.
    """
    logger.info("Market request for symbol=%s", symbol)

    try:
        tick = connection_manager.fetch_symbol_tick(symbol)
        info = connection_manager.fetch_symbol_info(symbol)
    except Exception as exc:
        logger.exception("Failed to fetch market data for %s: %s", symbol, exc)
        return None

    # Both may be falsy (None/empty)
    if not tick and not info:
        logger.info("Market data unavailable for symbol=%s", symbol)
        return None

    # Normalize and defensively access dicts
    bid = tick.get("bid") if isinstance(tick, dict) else None
    ask = tick.get("ask") if isinstance(tick, dict) else None
    spread = None
    if bid is not None and ask is not None:
        try:
            spread = ask - bid
        except Exception:
            spread = None

    result = {
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "time": tick.get("time") if isinstance(tick, dict) else None,
        "digits": info.get("digits") if isinstance(info, dict) else None,
        "point": info.get("point") if isinstance(info, dict) else None,
        "volume": tick.get("volume") if isinstance(tick, dict) else None,
        "high": info.get("high") if isinstance(info, dict) else None,
        "low": info.get("low") if isinstance(info, dict) else None,
    }
    return result


def get_bars(symbol: str, timeframe: str, count: int) -> Dict[str, Any]:
    """Return validated broker OHLC bars without filling data gaps."""
    raw_rates = connection_manager.fetch_symbol_rates(symbol, timeframe, count=count)
    bars: List[Dict[str, Any]] = []

    for raw in raw_rates:
        if not isinstance(raw, dict):
            continue
        try:
            timestamp = int(raw["time"])
            open_price = float(raw["open"])
            high = float(raw["high"])
            low = float(raw["low"])
            close = float(raw["close"])
            tick_volume = int(raw.get("tick_volume", 0))
            spread = int(raw.get("spread", 0))
            real_volume = int(raw.get("real_volume", 0))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        prices = (open_price, high, low, close)
        if timestamp <= 0 or not all(math.isfinite(price) for price in prices):
            continue
        if high < max(open_price, close) or low > min(open_price, close) or high < low:
            continue
        bars.append({
            "time": timestamp,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "tickVolume": max(0, tick_volume),
            "spreadPoints": max(0, spread),
            "realVolume": max(0, real_volume),
        })

    bars.sort(key=lambda item: item["time"])
    deduplicated = {bar["time"]: bar for bar in bars}
    normalized = list(deduplicated.values())
    return {
        "schemaVersion": "1.0",
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "priceBasis": "BID",
        "source": "LOCAL_MT5",
        "barCount": len(normalized),
        "bars": normalized,
    }
