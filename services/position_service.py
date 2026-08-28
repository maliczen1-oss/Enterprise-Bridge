# services/position_service.py
from typing import List, Dict, Any
import logging

from core.connection_manager import manager as connection_manager

logger = logging.getLogger("bridge")


def _first_present(source: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return None


def get_positions() -> List[Dict[str, Any]]:
    """
    Return open positions normalized to the Bridge API shape.

    Returns an empty list when positions are unavailable, malformed, or the
    bridge is not connected. Defensive against varying MT5 SDK shapes.
    """
    logger.info("Positions request")
    try:
        raw = connection_manager.fetch_positions()
    except Exception as exc:
        logger.exception("Failed to fetch positions from connection manager: %s", exc)
        return []

    if not raw:
        return []

    out: List[Dict[str, Any]] = []

    for p in raw:
        if not isinstance(p, dict):
            logger.debug("Skipping non-dict position entry: %r", p)
            continue

        pos = {
            "ticket": _first_present(p, "ticket", "position", "ticket_id"),
            "symbol": _first_present(p, "symbol", "name"),
            "volume": _first_present(p, "volume", "lots", "lot_size"),
            "price_open": _first_present(p, "price_open", "open_price", "price"),
            "price_current": _first_present(p, "price", "current_price", "price_current"),
            "stop_loss": _first_present(p, "sl", "stop_loss", "stopLoss"),
            "take_profit": _first_present(p, "tp", "take_profit", "takeProfit"),
            "swap": p.get("swap"),
            "profit": p.get("profit"),
            "comment": p.get("comment"),
            # Time fields vary by MT5 build; prefer `time` then `time_setup` then `open_time`.
            "time": _first_present(p, "time", "time_setup", "open_time"),
            # direction / type may be numeric or string depending on SDK
            "type": _first_present(p, "type", "position_type", "side"),
        }
        out.append(pos)

    return out
