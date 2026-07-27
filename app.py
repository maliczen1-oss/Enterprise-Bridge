# app.py
from fastapi import FastAPI
from core.connection_manager import manager as connection_manager
import logging

from middleware.auth import AuthenticationMiddleware

from api.health import router as health_router
from api.account import router as account_router
from api.positions import router as positions_router
from api.symbols import router as symbols_router
from api.market import router as market_router
from api.history import router as history_router
from api.trade import router as trade_router

logger = logging.getLogger("bridge")

app = FastAPI(title="WealthBuilder Bridge")

# Authentication middleware must be registered before routers are included so
# that it intercepts every request before it reaches a route handler. All
# routes are protected except those listed in middleware.auth.EXEMPT_PATHS
# (/health, /docs, /redoc, /openapi.json).
app.add_middleware(AuthenticationMiddleware)

# Public: no authentication required.
app.include_router(health_router)

# Protected: require a valid Bearer token (enforced by AuthenticationMiddleware).
app.include_router(account_router, prefix="/api", tags=["Account"])
app.include_router(positions_router, prefix="/api", tags=["Positions"])
app.include_router(symbols_router, prefix="/api", tags=["Symbols"])
app.include_router(market_router, prefix="/api", tags=["Market"])
app.include_router(history_router, prefix="/api", tags=["History"])
# trade.py already declares prefix="/trade" on its own router, so the
# resulting paths are /api/trade/... — do not add a duplicate "/trade" prefix here.
app.include_router(trade_router, prefix="/api", tags=["Trade"])

@app.on_event("startup")
async def on_startup():
    logger.info("Application startup event")
    # Start connection manager in a background thread to avoid blocking startup
    import threading
    t = threading.Thread(target=connection_manager.start, name="mt5-start", daemon=True)
    t.start()

@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Application shutdown event")
    # Stop connection manager synchronously to ensure clean shutdown
    connection_manager.stop()
