"""
HistoryService — historical deal and order retrieval.

Phase 2.1: Interface definition only.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class HistoryService:
    """
    Provides access to broker trading history.

    Responsibilities
    ----------------
    - Retrieve closed deals within a date range.
    - Retrieve filled and cancelled orders within a date range.

    Out of scope (Phase 2.2+)
    -------------------------
    - Broker connection management.
    - Error recovery and retry logic.
    """

    async def get_deals(
        self,
        date_from: datetime,
        date_to: datetime,
    ) -> list[dict[str, Any]]:
        """
        Return all closed deals between ``date_from`` and ``date_to``.

        Parameters
        ----------
        date_from:
            Start of the query range (UTC).
        date_to:
            End of the query range (UTC).

        Returns
        -------
        list[dict]
            One dict per deal: ticket, order, symbol, type, volume, price,
            commission, swap, profit, time, comment.

        Raises
        ------
        NotImplementedError
            Broker retrieval is not implemented in Phase 2.1.
        """
        logger.debug(
            "HistoryService.get_deals called.",
            extra={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        )
        raise NotImplementedError("HistoryService.get_deals: Phase 2.2.")

    async def get_orders(
        self,
        date_from: datetime,
        date_to: datetime,
    ) -> list[dict[str, Any]]:
        """
        Return all historical orders (filled and cancelled) between ``date_from``
        and ``date_to``.

        Parameters
        ----------
        date_from:
            Start of the query range (UTC).
        date_to:
            End of the query range (UTC).

        Returns
        -------
        list[dict]
            One dict per order: ticket, symbol, type, state, volume, price,
            stop_loss, take_profit, time_setup, time_done, comment.

        Raises
        ------
        NotImplementedError
            Broker retrieval is not implemented in Phase 2.1.
        """
        logger.debug(
            "HistoryService.get_orders called.",
            extra={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        )
        raise NotImplementedError("HistoryService.get_orders: Phase 2.2.")
