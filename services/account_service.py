"""
AccountService — broker account operations.

Phase 2.1: Interface definition only.  Method bodies raise ``NotImplementedError``
as a compile-time-safe marker for Phase 2.2 implementation.  The public API
is final; no signature changes are expected in subsequent phases.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AccountService:
    """
    Provides broker account information.

    Responsibilities
    ----------------
    - Retrieve account metadata (login, server, currency, leverage).
    - Retrieve real-time balance, equity, margin, and free margin.

    Out of scope (Phase 2.2+)
    -------------------------
    - Establishing the broker connection.
    - Error recovery and retry logic.
    """

    async def get_account_info(self) -> dict[str, Any]:
        """
        Return full account metadata from the broker.

        Returns
        -------
        dict
            Broker account fields (login, server, name, currency, leverage, …).

        Raises
        ------
        NotImplementedError
            Broker retrieval is not implemented in Phase 2.1.
        """
        logger.debug("AccountService.get_account_info called.")
        raise NotImplementedError("AccountService.get_account_info: Phase 2.2.")

    async def get_balance(self) -> dict[str, Any]:
        """
        Return the current account balance and equity.

        Returns
        -------
        dict
            ``balance``, ``equity``, ``profit`` fields.

        Raises
        ------
        NotImplementedError
            Broker retrieval is not implemented in Phase 2.1.
        """
        logger.debug("AccountService.get_balance called.")
        raise NotImplementedError("AccountService.get_balance: Phase 2.2.")

    async def get_margin_info(self) -> dict[str, Any]:
        """
        Return used margin, free margin, and margin level.

        Returns
        -------
        dict
            ``margin``, ``margin_free``, ``margin_level`` fields.

        Raises
        ------
        NotImplementedError
            Broker retrieval is not implemented in Phase 2.1.
        """
        logger.debug("AccountService.get_margin_info called.")
        raise NotImplementedError("AccountService.get_margin_info: Phase 2.2.")
