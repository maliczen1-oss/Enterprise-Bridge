"""
SymbolService — trading symbol catalogue operations.

Phase 2.1: Interface definition only.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SymbolService:
    """
    Provides the broker trading symbol catalogue.

    Responsibilities
    ----------------
    - Retrieve all symbols available on the broker.
    - Retrieve the full specification for a single named symbol.

    Out of scope (Phase 2.2+)
    -------------------------
    - Symbol subscription management.
    - Error recovery and retry logic.
    """

    async def get_all_symbols(self) -> list[dict[str, Any]]:
        """
        Return all symbols available on the connected broker.

        Returns
        -------
        list[dict]
            One dict per symbol with name, description, and classification fields.

        Raises
        ------
        NotImplementedError
            Broker retrieval is not implemented in Phase 2.1.
        """
        logger.debug("SymbolService.get_all_symbols called.")
        raise NotImplementedError("SymbolService.get_all_symbols: Phase 2.2.")

    async def get_symbol_info(self, symbol: str) -> dict[str, Any]:
        """
        Return the full specification for a named trading symbol.

        Parameters
        ----------
        symbol:
            The broker symbol name (e.g. ``"EURUSD"``).

        Returns
        -------
        dict
            Symbol specification fields: digits, contract size, margin requirements, etc.

        Raises
        ------
        NotImplementedError
            Broker retrieval is not implemented in Phase 2.1.
        """
        logger.debug("SymbolService.get_symbol_info called.", extra={"symbol": symbol})
        raise NotImplementedError("SymbolService.get_symbol_info: Phase 2.2.")
