# Architecture Report — WealthBuilder Bridge Phase 2.1

## Overview

The WealthBuilder Bridge is a standalone FastAPI application whose sole
responsibility is broker communication.  Risk calculation, signal generation,
lot sizing, and market analysis remain inside WealthBuilder OS.  The bridge
exposes broker functionality over a secure, authenticated REST API.

Phase 2.1 delivers the complete enterprise foundation.  No MetaTrader5 code,
no broker communication, and no trading logic are present.

---

## Layer diagram

```
┌──────────────────────────────────────────────────────────────┐
│  ASGI Entry Point  (bridge/app.py)                           │
│  FastAPI + Uvicorn                                           │
└────────────────────┬─────────────────────────────────────────┘
                     │
         ┌───────────▼───────────┐
         │     Middleware Stack   │
         │  (outermost → inner)   │
         │  1. RequestID          │  Assigns UUID per request
         │  2. Timing             │  Wall-clock measurement
         │  3. AccessLog          │  Structured per-request log
         │  4. Authentication     │  Bearer token enforcement
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │     API Routers        │
         │  health   (public)     │  GET /health
         │  account  (protected)  │  GET /api/account/*
         │  positions             │  GET /api/positions/*
         │  symbols               │  GET /api/symbols/*
         │  market                │  GET /api/market/*
         │  trade                 │  POST|PUT|DELETE /api/trade/*
         │  history               │  GET /api/history/*
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │     Service Layer      │
         │  AccountService        │
         │  PositionService       │
         │  MarketService         │
         │  SymbolService         │
         │  TradeService          │
         │  HistoryService        │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │     Core / Shared      │
         │  BridgeResponse        │  Single response envelope
         │  Exception hierarchy   │  BridgeBaseException tree
         │  ConnectionManager     │  Lifecycle state machine
         │  Structured logging    │  JSON via contextvars
         │  Settings              │  Env-var configuration
         └───────────────────────┘
```

---

## Key design decisions

### 1. Single response envelope
Every endpoint returns the same `BridgeResponse` model:
`{ success, requestId, timestamp, data, error }`.  No endpoint-specific
wrappers exist.  This eliminates response shape inconsistency across versions.

### 2. Middleware-first authentication
Authentication is enforced at the ASGI middleware layer, not per-route.
A single `AuthenticationMiddleware` short-circuits the pipeline before any
route handler is invoked.  The exempt path list (`/health`, `/docs`,
`/redoc`, `/openapi.json`) is the canonical source of truth.

### 3. contextvars for request ID propagation
The `X-Request-ID` UUID is stored in a `contextvars.ContextVar` so it is
accessible everywhere in the async call stack — including the structured log
formatter — without being threaded through function parameters.

### 4. Exception hierarchy with a single handler
All domain exceptions inherit from `BridgeBaseException`.  A single
`@app.exception_handler(BridgeBaseException)` converts every domain error
into the standard response envelope.  Stack traces never reach the caller.

### 5. ConnectionManager as state machine only
`ConnectionManager` tracks lifecycle state
(DISCONNECTED → INITIALIZING → READY → SHUTTING_DOWN → DISCONNECTED)
with no broker I/O.  The `start()` / `stop()` hooks are the only touch points
Phase 2.2 needs to fill in.

### 6. Service layer as typed interface
All six service classes expose fully-typed public methods that raise
`NotImplementedError`.  This gives Phase 2.2 a clean, compiler-enforced
contract without any stub or placeholder logic leaking into the API layer.

### 7. Environment-only configuration
`config.py` reads exclusively from environment variables (loaded from `.env`
via `python-dotenv`).  All required variables are validated with descriptive
`ConfigurationException` messages at startup — misconfiguration fails fast.

---

## Module inventory

| Path | Responsibility |
|------|---------------|
| `bridge/app.py` | FastAPI app, middleware registration, routers, exception handlers, lifespan |
| `bridge/config.py` | Settings singleton validated at import time |
| `bridge/__main__.py` | `python -m bridge` entry point |
| `bridge/core/models.py` | `BridgeResponse`, `HealthData` Pydantic models |
| `bridge/core/responses.py` | `success_response`, `error_response`, `not_implemented_response` builders |
| `bridge/core/exceptions.py` | `BridgeBaseException` + 4 subclasses |
| `bridge/core/logging.py` | `configure_logging`, `get_logger`, `_StructuredFormatter` |
| `bridge/core/request_context.py` | `ContextVar` for request ID propagation |
| `bridge/core/auth.py` | `require_auth` FastAPI dependency |
| `bridge/core/connection_manager.py` | `BridgeState` enum + `ConnectionManager` lifecycle |
| `bridge/middleware/request_id.py` | UUID assignment, `X-Request-ID` header |
| `bridge/middleware/timing.py` | `X-Process-Time-Ms` header |
| `bridge/middleware/logging.py` | Structured access log per request |
| `bridge/middleware/auth.py` | Bearer token enforcement with exempt path list |
| `bridge/api/health.py` | `GET /health` — only functional endpoint |
| `bridge/api/account.py` | Account router — 501 stubs |
| `bridge/api/positions.py` | Positions router — 501 stubs |
| `bridge/api/symbols.py` | Symbols router — 501 stubs |
| `bridge/api/market.py` | Market data router — 501 stubs |
| `bridge/api/trade.py` | Trade execution router — 501 stubs |
| `bridge/api/history.py` | History router — 501 stubs |
| `bridge/services/account_service.py` | `AccountService` interface |
| `bridge/services/position_service.py` | `PositionService` interface |
| `bridge/services/market_service.py` | `MarketService` interface |
| `bridge/services/symbol_service.py` | `SymbolService` interface |
| `bridge/services/trade_service.py` | `TradeService` interface |
| `bridge/services/history_service.py` | `HistoryService` interface |
| `bridge/tests/test_bridge.py` | 66-test suite covering all Phase 2.1 criteria |
| `bridge/tests/conftest.py` | Session-scoped app state bootstrap |

---

## Phase 2.2 integration points

Phase 2.2 must touch exactly these locations:

1. **`ConnectionManager.start()` / `stop()`** — add broker connect / disconnect calls.
2. **Each `*Service` method** — replace `raise NotImplementedError(...)` with broker calls.
3. **Each `api/*.py` router** — replace `not_implemented_response(...)` with service calls.
4. **`requirements.txt`** — add the broker SDK dependency (e.g. `MetaTrader5`).

Nothing in the core, middleware, or configuration layer requires modification.
