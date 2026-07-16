"""
PositionService — open position operations.

Phase 2.1: Interface definition only.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PositionService:
    """
    Provides access to open broker positions.

    Responsibilities
    ----------------
    - Retrieve all open positions.
    - Retrieve a single position by broker ticket number.

    Out of scope (Phase 2.2+)
    -------------------------
    - Modifying or closing positions (delegated to TradeService).
    - Error recovery and retry logic.
    """

    async def get_all_positions(self) -> list[dict[str, Any]]:
        """
        Return all currently open positions.

        Returns
        -------
        list[dict]
            One dict per position with standard position fields.

        Raises
        ------
        NotImplementedError
            Broker retrieval is not implemented in Phase 2.1.
        """
        logger.debug("PositionService.get_all_positions called.")
        raise NotImplementedError("PositionService.get_all_positions: Phase 2.2.")

    async def get_position_by_ticket(self, ticket: int) -> dict[str, Any]:
        """
        Return a single open position by its broker ticket number.

        Parameters
        ----------
        ticket:
            The broker-assigned unique ticket number for the position.

        Returns
        -------
        dict
            Position fields for the requested ticket.

        Raises
        ------
        NotImplementedError
            Broker retrieval is not implemented in Phase 2.1.
        """
        logger.debug("PositionService.get_position_by_ticket called.", extra={"ticket": ticket})
        raise NotImplementedError("PositionService.get_position_by_ticket: Phase 2.2.")
