"""
TradeService — order execution and position management.

Phase 3.3 decision: this repository is certified as read-only for trading in
Atlas Certification Phase 3.3. The service surface remains present to satisfy
the Phase 2.x/3.x contract, but all methods raise ``NotImplementedException``
from ``core.exceptions`` to make the read-only intent explicit and
machine-identifiable. API handlers map that exception to a canonical 501
response envelope.
"""

from __future__ import annotations

import logging
from typing import Any

from core.exceptions import NotImplementedException

logger = logging.getLogger(__name__)


class TradeService:
    """
    Provides order execution and open position management.

    Responsibilities
    ----------------
    - Open market and pending orders.
    - Modify stop-loss and take-profit on open positions.
    - Close open positions.

    Operational note (Phase 3.3)
    ----------------------------
    This deployment is intentionally read-only for trading. All public methods
    raise ``NotImplementedException`` which is mapped by the API layer to a
    canonical HTTP 501 BridgeResponse envelope. The explicit exception type
    prevents accidental leakage of implementation details and makes the
    behaviour machine-detectable by integration tests and operator tooling.
    """

    async def open_trade(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        """
        Send a market or pending order to the broker.

        In Phase 3.3 this method intentionally refuses to execute trades.
        """
        logger.debug("TradeService.open_trade called.")
        raise NotImplementedException("Trade execution disabled in Phase 3.3.")

    async def modify_trade(
        self,
        ticket: int,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> dict[str, Any]:
        """
        Modify the stop-loss or take-profit of an open position.

        In Phase 3.3 this method intentionally refuses to modify trades.
        """
        logger.debug("TradeService.modify_trade called.", extra={"ticket": ticket})
        raise NotImplementedException("Trade modification disabled in Phase 3.3.")

    async def close_trade(self, ticket: int) -> dict[str, Any]:
        """
        Send a close order for an open position.

        In Phase 3.3 this method intentionally refuses to close trades.
        """
        logger.debug("TradeService.close_trade called.", extra={"ticket": ticket})
        raise NotImplementedException("Trade close disabled in Phase 3.3.")
