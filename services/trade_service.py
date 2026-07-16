"""
TradeService — order execution and position management.

Phase 2.1: Interface definition only.

Note: No buy/sell/modify/close logic is implemented in this phase.
This service class exists solely to establish the public contract for
Phase 2.2 implementation.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TradeService:
    """
    Provides order execution and open position management.

    Responsibilities
    ----------------
    - Open market and pending orders.
    - Modify stop-loss and take-profit on open positions.
    - Close open positions.

    Out of scope (Phase 2.2+)
    -------------------------
    - All broker communication.
    - Error recovery and retry logic.
    - Risk validation (handled upstream by WealthBuilder OS).
    """

    async def open_trade(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        """
        Send a market or pending order to the broker.

        Parameters
        ----------
        request_payload:
            Validated trade request including symbol, order type, volume,
            price, stop-loss, take-profit, and comment fields.

        Returns
        -------
        dict
            Broker confirmation fields: order ticket, execution price, time.

        Raises
        ------
        NotImplementedError
            Broker execution is not implemented in Phase 2.1.
        """
        logger.debug("TradeService.open_trade called.")
        raise NotImplementedError("TradeService.open_trade: Phase 2.2.")

    async def modify_trade(
        self,
        ticket: int,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> dict[str, Any]:
        """
        Modify the stop-loss or take-profit of an open position.

        Parameters
        ----------
        ticket:
            The broker-assigned ticket number for the target position.
        stop_loss:
            New stop-loss price.  Pass ``None`` to leave unchanged.
        take_profit:
            New take-profit price.  Pass ``None`` to leave unchanged.

        Returns
        -------
        dict
            Broker confirmation of the modification.

        Raises
        ------
        NotImplementedError
            Broker execution is not implemented in Phase 2.1.
        """
        logger.debug("TradeService.modify_trade called.", extra={"ticket": ticket})
        raise NotImplementedError("TradeService.modify_trade: Phase 2.2.")

    async def close_trade(self, ticket: int) -> dict[str, Any]:
        """
        Send a close order for an open position.

        Parameters
        ----------
        ticket:
            The broker-assigned ticket number for the position to close.

        Returns
        -------
        dict
            Broker confirmation: close price, close time, profit.

        Raises
        ------
        NotImplementedError
            Broker execution is not implemented in Phase 2.1.
        """
        logger.debug("TradeService.close_trade called.", extra={"ticket": ticket})
        raise NotImplementedError("TradeService.close_trade: Phase 2.2.")
