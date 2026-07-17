# app.py
from fastapi import FastAPI
from core.connection_manager import manager as connection_manager
import logging

logger = logging.getLogger("bridge")

app = FastAPI(title="WealthBuilder Bridge")

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
