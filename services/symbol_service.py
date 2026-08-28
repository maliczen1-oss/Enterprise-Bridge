# services/symbol_service.py
from typing import List, Dict, Any
import logging

from core.connection_manager import manager as connection_manager

logger = logging.getLogger("bridge")


def _first_present(source: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return None


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
            "name": _first_present(s, "name", "symbol"),
            "visible": s.get("visible") if s.get("visible") is not None else True,
            "trade_mode": _first_present(s, "trade_mode", "trade"),
            "digits": s.get("digits"),
            "point": s.get("point"),
            "spread": s.get("spread"),
            "contract_size": _first_present(s, "contract_size", "lot_size"),
            "currency": _first_present(s, "currency", "currency_base"),
        }
        out.append(sym)
    return out
