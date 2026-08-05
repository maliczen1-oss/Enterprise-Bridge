# services/history_service.py
from typing import List, Dict, Any, Optional
import logging
import datetime

from core.connection_manager import manager as connection_manager

logger = logging.getLogger("bridge")


def _safe_list(val: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    return val if isinstance(val, list) else []


def get_history(
    from_dt: datetime.datetime,
    to_dt: datetime.datetime,
    ticket: Optional[int] = None,
    symbol: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return history (deals and orders) within the date range. Limit is applied after retrieval.

    Defensive: handles None/empty returns from the connection manager and normalizes
    minimal fields for API consumption.
    """
    logger.info("History request from=%s to=%s ticket=%s symbol=%s limit=%s", from_dt.isoformat(), to_dt.isoformat(), ticket, symbol, limit)

    try:
        deals = _safe_list(connection_manager.fetch_history_deals(from_dt, to_dt, ticket=ticket, symbol=symbol))
    except Exception as exc:
        logger.exception("Failed to fetch history deals: %s", exc)
        deals = []

    try:
        orders = _safe_list(connection_manager.fetch_history_orders(from_dt, to_dt, ticket=ticket, symbol=symbol))
    except Exception as exc:
        logger.exception("Failed to fetch history orders: %s", exc)
        orders = []

    # Apply limit if provided
    if limit is not None and isinstance(limit, int) and limit > 0:
        deals = deals[:limit]
        orders = orders[:limit]

    # Normalize minimal fields requested
    def normalize_deal(d: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(d, dict):
            return {}
        return {
            "ticket": d.get("ticket"),
            "symbol": d.get("symbol"),
            "profit": d.get("profit"),
            "commission": d.get("commission"),
            "swap": d.get("swap"),
            "comment": d.get("comment"),
            "close_time": d.get("time") or d.get("time_done"),
        }

    def normalize_order(o: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(o, dict):
            return {}
        return {
            "ticket": o.get("ticket"),
            "symbol": o.get("symbol"),
            "profit": o.get("profit"),
            "commission": o.get("commission"),
            "swap": o.get("swap"),
            "comment": o.get("comment"),
            "close_time": o.get("time") or o.get("time_done"),
        }

    normalized_deals = [normalize_deal(d) for d in deals]
    normalized_orders = [normalize_order(o) for o in orders]

    return {
        "deals": normalized_deals,
        "orders": normalized_orders,
    }
