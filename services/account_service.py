# services/account_service.py
from typing import Optional, Dict, Any
import logging

from core.connection_manager import manager as connection_manager

logger = logging.getLogger("bridge")


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
        "account": info.get("login") or info.get("login_id") or info.get("account"),
        "server": info.get("server"),
        "broker": info.get("company"),
        "balance": info.get("balance"),
        "equity": info.get("equity"),
        "margin": info.get("margin"),
        "free_margin": info.get("margin_free") or info.get("free_margin"),
        "margin_level": info.get("margin_level"),
        "currency": info.get("currency"),
        "leverage": info.get("leverage"),
        "company": info.get("company"),
        "account_name": info.get("name") or info.get("login_name"),
    }
    return account
