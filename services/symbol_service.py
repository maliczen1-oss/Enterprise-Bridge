# services/symbol_service.py
from typing import List, Dict, Any
import logging

from core.connection_manager import manager as connection_manager

logger = logging.getLogger("bridge")


def get_symbols() -> List[Dict[str, Any]]:
    """
    Return available symbols with requested attributes.

    Defensive: returns an empty list when no symbols are available or on error.
    """
    logger.info("Symbol request")
    try:
        raw = connection_manager.fetch_symbols()
    except Exception as exc:
        logger.exception("Failed to fetch symbols: %s", exc)
        return []

    if not raw:
        return []

    out: List[Dict[str, Any]] = []
    for s in raw:
        if not isinstance(s, dict):
            logger.debug("Skipping non-dict symbol entry: %r", s)
            continue
        sym = {
            "name": s.get("name") or s.get("symbol"),
            "visible": s.get("visible") if s.get("visible") is not None else True,
            "trade_mode": s.get("trade_mode") or s.get("trade"),
            "digits": s.get("digits"),
            "point": s.get("point"),
            "spread": s.get("spread"),
            "contract_size": s.get("contract_size") or s.get("lot_size"),
            "currency": s.get("currency_base") or s.get("currency"),
        }
        out.append(sym)
    return out
