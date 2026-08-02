# services/position_service.py
from typing import List, Dict, Any
import logging

from core.connection_manager import manager as connection_manager

logger = logging.getLogger("bridge")


def get_positions() -> List[Dict[str, Any]]:
    """
    Return open positions normalized to the Bridge API shape.
    Returns an empty list when positions are unavailable or the bridge is not connected.
    """
    logger.info("Positions request")
    raw = connection_manager.fetch_positions()
    out: List[Dict[str, Any]] = []

    for p in raw:
        pos = {
            "ticket": p.get("ticket") or p.get("position") or p.get("ticket_id"),
            "symbol": p.get("symbol") or p.get("name"),
            "volume": p.get("volume") or p.get("lots") or p.get("lot_size"),
            "price_open": p.get("price_open") or p.get("open_price") or p.get("price"),
            "price_current": p.get("price") or p.get("current_price") or p.get("price_current"),
            "swap": p.get("swap"),
            "profit": p.get("profit"),
            "comment": p.get("comment"),
            # Time fields vary by MT5 build; prefer `time` then `time_setup` then `open_time`.
            "time": p.get("time") or p.get("time_setup") or p.get("open_time"),
            # direction / type may be numeric or string depending on SDK
            "type": p.get("type") or p.get("position_type") or p.get("side"),
        }
        out.append(pos)

    return out
