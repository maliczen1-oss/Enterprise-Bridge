# services/account_service.py
from typing import Optional, Dict, Any
import logging

from core.connection_manager import manager as connection_manager

logger = logging.getLogger("bridge")


def _first_present(source: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return None


def get_account() -> Optional[Dict[str, Any]]:
    """
    Return account metadata and balances. Returns None if unavailable.
    """
    logger.info("Account request")
    info = connection_manager.fetch_account()
    if not info or not isinstance(info, dict):
        logger.info("Account data unavailable or malformed")
        return None

    # Map fields to the requested output shape. MT5 account_info fields vary by build.
    account = {
        "account": _first_present(info, "login", "login_id", "account"),
        "server": info.get("server"),
        "broker": info.get("company"),
        "balance": info.get("balance"),
        "equity": info.get("equity"),
        "margin": info.get("margin"),
        "free_margin": _first_present(info, "margin_free", "free_margin"),
        "margin_level": info.get("margin_level"),
        "currency": info.get("currency"),
        "leverage": info.get("leverage"),
        "company": info.get("company"),
        "account_name": _first_present(info, "name", "login_name"),
    }
    return account
