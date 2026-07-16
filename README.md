# WealthBuilder Bridge — Phase 2.1

> **Enterprise broker communication layer for WealthBuilder OS.**

The WealthBuilder Bridge is a standalone FastAPI service whose sole
responsibility is exposing broker functionality over a secure REST API.
Risk calculation, signal generation, and position sizing remain inside
WealthBuilder OS — the bridge knows nothing about strategy.

Phase 2.1 delivers the complete enterprise foundation.  MT5 connectivity
and live broker communication are implemented in Phase 2.2 and later.

---

## Table of contents

1. [Architecture](#architecture)
2. [Quick start](#quick-start)
3. [Configuration](#configuration)
4. [API reference](#api-reference)
5. [Authentication](#authentication)
6. [Running tests](#running-tests)
7. [Project structure](#project-structure)
8. [Engineering notes](#engineering-notes)

---

## Architecture

```
bridge/
├── app.py                    # FastAPI application, middleware, routers, exception handlers
├── config.py                 # Environment-driven settings (validated at startup)
├── __main__.py               # python -m bridge entry point
│
├── api/                      # Route handlers (thin — delegate to services)
│   ├── health.py             # GET /health (public, no auth)
│   ├── account.py            # GET /api/account/*
│   ├── positions.py          # GET /api/positions/*
│   ├── symbols.py            # GET /api/symbols/*
│   ├── market.py             # GET /api/market/*
│   ├── trade.py              # POST/PUT/DELETE /api/trade/*
│   └── history.py            # GET /api/history/*
│
├── core/                     # Shared infrastructure
│   ├── auth.py               # Bearer token FastAPI dependency
│   ├── connection_manager.py # Lifecycle state machine (DISCONNECTED → READY)
│   ├── exceptions.py         # Exception hierarchy
│   ├── logging.py            # Structured JSON logging
│   ├── models.py             # BridgeResponse, HealthData (Pydantic)
│   ├── request_context.py    # contextvars-based request ID propagation
│   └── responses.py          # Response builder helpers
│
├── middleware/               # Starlette ASGI middleware (outermost → innermost)
│   ├── request_id.py         # Generate / propagate X-Request-ID
│   ├── timing.py             # Measure and expose X-Process-Time-Ms
│   ├── logging.py            # Structured access log per request
│   └── auth.py               # Bearer token enforcement (short-circuits on failure)
│
├── services/                 # Business-logic layer (Phase 2.2+ implementations)
│   ├── account_service.py
│   ├── market_service.py
│   ├── position_service.py
│   ├── symbol_service.py
│   ├── trade_service.py
│   └── history_service.py
│
├── tests/
│   └── test_bridge.py        # Full Phase 2.1 test suite
│
├── logs/                     # Log file output directory (not committed)
├── .env.example              # Environment variable template
├── requirements.txt          # Pinned Python dependencies
└── README.md                 # This file
```

### Middleware execution order

Middleware is registered inner → outer in `app.py`; it executes outer → inner
per request:

```
Incoming request
  │
  ▼  RequestIDMiddleware     — assigns X-Request-ID
  ▼  TimingMiddleware        — starts wall-clock timer
  ▼  AccessLogMiddleware     — records request on completion
  ▼  AuthenticationMiddleware — enforces Bearer token (short-circuits on failure)
  ▼
  Route handler
```

---

## Quick start

### Prerequisites

- Python 3.12 or later
- `pip` (or `uv` / `pipenv`)

### Installation

```bash
# Clone and enter the bridge directory
cd bridge

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure the environment
cp .env.example .env
# Edit .env — set AUTH_TOKEN to a strong random value at minimum
```

### Run the server

```bash
# From the repository root
python -m bridge

# Or directly with uvicorn
uvicorn bridge.app:app --host 0.0.0.0 --port 8001
```

The server will log startup events to stdout and be available at:

| Interface | URL                              |
|-----------|----------------------------------|
| Swagger   | http://localhost:8001/docs       |
| ReDoc     | http://localhost:8001/redoc      |
| OpenAPI   | http://localhost:8001/openapi.json |
| Health    | http://localhost:8001/health     |

---

## Configuration

All configuration is read from environment variables.  A `.env` file in the
`bridge/` directory is loaded automatically if present.

| Variable          | Required | Default       | Description                                                   |
|-------------------|----------|---------------|---------------------------------------------------------------|
| `HOST`            | No       | `0.0.0.0`     | Bind address for the Uvicorn server.                          |
| `PORT`            | No       | `8000`        | Bind port for the Uvicorn server.                             |
| `ENVIRONMENT`     | **Yes**  | —             | One of `development`, `staging`, `production`.                |
| `API_VERSION`     | **Yes**  | —             | API version string (e.g. `v1`).                               |
| `LOG_LEVEL`       | No       | `INFO`        | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.       |
| `AUTH_TOKEN`      | **Yes**  | —             | Secret bearer token for all protected endpoints.              |
| `REQUEST_TIMEOUT` | No       | `30`          | Upstream I/O timeout in seconds (Phase 2.2+ only).            |

Generate a secure `AUTH_TOKEN`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## API reference

### Public endpoints

| Method | Path      | Auth | Description                     |
|--------|-----------|------|---------------------------------|
| GET    | `/health` | No   | Bridge health and uptime status |
| GET    | `/docs`   | No   | Swagger UI                      |
| GET    | `/redoc`  | No   | ReDoc UI                        |

### Protected endpoints (Phase 2.1 — return HTTP 501)

| Method | Path                       | Description                     |
|--------|----------------------------|---------------------------------|
| GET    | `/api/account`             | Account metadata                |
| GET    | `/api/account/balance`     | Balance and equity              |
| GET    | `/api/account/margin`      | Margin information              |
| GET    | `/api/positions`           | List open positions             |
| GET    | `/api/positions/{ticket}`  | Single position by ticket       |
| GET    | `/api/symbols`             | List available symbols          |
| GET    | `/api/symbols/{symbol}`    | Symbol specification            |
| GET    | `/api/market/{symbol}/tick`| Latest bid/ask tick             |
| GET    | `/api/market/{symbol}/rates`| OHLCV rate history             |
| POST   | `/api/trade/open`          | Open a new trade                |
| PUT    | `/api/trade/{ticket}/modify` | Modify stop-loss / take-profit |
| DELETE | `/api/trade/{ticket}/close` | Close an open position         |
| GET    | `/api/history/deals`       | Historical deals                |
| GET    | `/api/history/orders`      | Historical orders               |

### Standard response envelope

Every endpoint returns the same JSON structure:

```json
{
  "success": true,
  "requestId": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T12:34:56.789Z",
  "data": { ... },
  "error": null
}
```

On failure:

```json
{
  "success": false,
  "requestId": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T12:34:56.789Z",
  "data": null,
  "error": {
    "code": "NOT_IMPLEMENTED",
    "message": "This endpoint will be implemented in a future phase."
  }
}
```

---

## Authentication

All endpoints except `GET /health` require a Bearer token:

```
Authorization: Bearer <AUTH_TOKEN>
```

Missing or invalid tokens receive:

```
HTTP/1.1 401 Unauthorized
X-Request-ID: <uuid>

{
  "success": false,
  "requestId": "...",
  "timestamp": "...",
  "data": null,
  "error": {
    "code": "AUTHENTICATION_FAILED",
    "message": "Missing or malformed Authorization header. Expected: Authorization: Bearer <token>"
  }
}
```

Tokens are **never** logged.

---

## Running tests

```bash
cd bridge
pip install -r requirements.txt
pytest -v
```

The test suite validates:

- Application starts and shuts down cleanly
- Swagger and ReDoc load
- `GET /health` returns HTTP 200
- All protected endpoints return HTTP 401 without a valid token
- All protected endpoints return HTTP 501 (not 500) with a valid token
- All modules compile without import errors

---

## Engineering notes

### No MT5 code
Phase 2.1 contains zero references to MetaTrader5, broker connections, or
trading logic.  The `ConnectionManager` maintains lifecycle state only.
Service classes expose their public API as typed method signatures; all method
bodies raise `NotImplementedError` as a compile-safe marker for Phase 2.2.

### Exception hierarchy
All custom exceptions inherit from `BridgeBaseException` so a single
`@app.exception_handler(BridgeBaseException)` covers all domain errors.
Stack traces are never serialised into responses.

### Structured logging
Every log record is a JSON object written to stdout.  The `request_id` field
is injected from a `contextvars.ContextVar` so it appears in every log line
produced during a request — including nested service calls — without parameter
threading.

### Request ID propagation
`RequestIDMiddleware` assigns a UUID v4 per request (or honours an incoming
`X-Request-ID` header for distributed tracing), stores it in
`request.state.request_id`, and propagates it via `contextvars` so every
component — middleware, route handlers, log formatter — reads the same value.

### Security invariants
- Secrets are never logged (search `logging.py` and `middleware/auth.py` —
  `credentials.credentials` is never passed to any log call).
- Stack traces are caught by the catch-all exception handler and discarded.
- Bearer token comparison uses `==` on strings of equal length; constant-time
  comparison (`hmac.compare_digest`) is recommended for production hardening
  in Phase 2.2+.
