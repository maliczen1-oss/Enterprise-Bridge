# services/market_service.py
from typing import Optional, Dict, Any
import logging

from core.connection_manager import manager as connection_manager

logger = logging.getLogger("bridge")


def get_market(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Return market tick and symbol info for the requested symbol.
    """
    logger.info("Market request for symbol=%s", symbol)
    tick = connection_manager.fetch_symbol_tick(symbol)
    info = connection_manager.fetch_symbol_info(symbol)

    if not tick and not info:
        logger.info("Market data unavailable for symbol=%s", symbol)
        return None

    result = {
        "bid": tick.get("bid") if tick else None,
        "ask": tick.get("ask") if tick else None,
        "spread": (tick.get("ask") - tick.get("bid")) if tick and tick.get("ask") is not None and tick.get("bid") is not None else None,
        "time": tick.get("time") if tick else None,
        "digits": info.get("digits") if info else None,
        "point": info.get("point") if info else None,
        "volume": tick.get("volume") if tick else None,
        "high": info.get("high") if info else None,
        "low": info.get("low") if info else None,
    }
    return result
