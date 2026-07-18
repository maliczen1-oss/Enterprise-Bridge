# services/symbol_service.py
from typing import List, Dict, Any
import logging

from core.connection_manager import manager as connection_manager

logger = logging.getLogger("bridge")


def get_symbols() -> List[Dict[str, Any]]:
    """
    Return available symbols with requested attributes.
    """
    logger.info("Symbol request")
    raw = connection_manager.fetch_symbols()
    out: List[Dict[str, Any]] = []
    for s in raw:
        sym = {
            "name": s.get("name") or s.get("symbol"),
            "visible": s.get("visible"),
            "trade_mode": s.get("trade_mode") or s.get("trade"),
            "digits": s.get("digits"),
            "point": s.get("point"),
            "spread": s.get("spread"),
            "contract_size": s.get("contract_size") or s.get("lot_size"),
            "currency": s.get("currency_base") or s.get("currency"),
        }
        out.append(sym)
    return out
