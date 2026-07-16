"""
Bridge connection manager — lifecycle state machine.

Tracks the operational state of the WealthBuilder Bridge itself.  No broker
connections are established in Phase 2.1; this module defines the state
machine and lifecycle hooks only.

States
------
DISCONNECTED  — initial state; no active connection.
INITIALIZING  — startup sequence is running.
READY         — the bridge is operational and accepting API calls.
SHUTTING_DOWN — graceful shutdown is in progress.
"""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class BridgeState(str, Enum):
    """Possible operational states of the WealthBuilder Bridge."""

    DISCONNECTED = "DISCONNECTED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    SHUTTING_DOWN = "SHUTTING_DOWN"


class ConnectionManager:
    """
    Manages the bridge lifecycle state.

    This class is instantiated once at application startup and shared via
    FastAPI's dependency-injection system (``app.state.connection_manager``).
    Broker-specific initialisation logic is deferred to Phase 2.2 and later.
    """

    def __init__(self) -> None:
        self._state: BridgeState = BridgeState.DISCONNECTED

    # ------------------------------------------------------------------
    # State accessors
    # ------------------------------------------------------------------

    @property
    def state(self) -> BridgeState:
        """Current lifecycle state of the bridge."""
        return self._state

    @property
    def is_ready(self) -> bool:
        """Return ``True`` when the bridge is in the READY state."""
        return self._state is BridgeState.READY

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        Execute the bridge startup sequence.

        Transitions: DISCONNECTED → INITIALIZING → READY.
        Broker initialisation is out of scope for Phase 2.1.
        """
        logger.info("Connection manager starting.", extra={"from_state": self._state.value})
        self._state = BridgeState.INITIALIZING
        # Phase 2.2+: establish broker connection here.
        self._state = BridgeState.READY
        logger.info("Connection manager ready.", extra={"state": self._state.value})

    async def stop(self) -> None:
        """
        Execute the bridge shutdown sequence.

        Transitions: READY → SHUTTING_DOWN → DISCONNECTED.
        """
        logger.info("Connection manager shutting down.", extra={"from_state": self._state.value})
        self._state = BridgeState.SHUTTING_DOWN
        # Phase 2.2+: cleanly disconnect from broker here.
        self._state = BridgeState.DISCONNECTED
        logger.info("Connection manager stopped.", extra={"state": self._state.value})
