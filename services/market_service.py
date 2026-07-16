"""
MarketService — live market data operations.

Phase 2.1: Interface definition only.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MarketService:
    """
    Provides live and historical market data from the broker.

    Responsibilities
    ----------------
    - Retrieve the latest bid/ask tick for a symbol.
    - Retrieve OHLCV candlestick rate history.

    Out of scope (Phase 2.2+)
    -------------------------
    - Real-time streaming subscriptions.
    - Error recovery and retry logic.
    """

    async def get_latest_tick(self, symbol: str) -> dict[str, Any]:
        """
        Return the most recent market tick for a trading symbol.

        Parameters
        ----------
        symbol:
            The broker symbol name (e.g. ``"EURUSD"``, ``"XAUUSD"``).

        Returns
        -------
        dict
            Tick fields: ``symbol``, ``time``, ``bid``, ``ask``, ``last``, ``volume``.

        Raises
        ------
        NotImplementedError
            Broker retrieval is not implemented in Phase 2.1.
        """
        logger.debug("MarketService.get_latest_tick called.", extra={"symbol": symbol})
        raise NotImplementedError("MarketService.get_latest_tick: Phase 2.2.")

    async def get_rates(
        self,
        symbol: str,
        timeframe: str,
        count: int,
    ) -> list[dict[str, Any]]:
        """
        Return OHLCV rate bars for a symbol and timeframe.

        Parameters
        ----------
        symbol:
            The broker symbol name.
        timeframe:
            The timeframe string (e.g. ``"M1"``, ``"H1"``, ``"D1"``).
        count:
            The number of bars to retrieve, counting back from the current bar.

        Returns
        -------
        list[dict]
            One dict per OHLCV bar: ``time``, ``open``, ``high``, ``low``,
            ``close``, ``tick_volume``, ``spread``, ``real_volume``.

        Raises
        ------
        NotImplementedError
            Broker retrieval is not implemented in Phase 2.1.
        """
        logger.debug(
            "MarketService.get_rates called.",
            extra={"symbol": symbol, "timeframe": timeframe, "count": count},
        )
        raise NotImplementedError("MarketService.get_rates: Phase 2.2.")
