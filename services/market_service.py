# services/market_service.py
from typing import Optional, Dict, Any
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
