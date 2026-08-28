# WealthBuilder Bridge — API Contract

**Version:** 2.1.0  
**API Version:** v1  
**Status:** HISTORICAL — Phase 2.1 baseline. The runtime contract has evolved; use the generated `/openapi.json`, the repository README, and `FOUNDER-OPERATIONS-RUNBOOK.md` for the current release.
**Effective date:** 2026-07-14  

---

## Contract governance

This document is the **single source of truth** for all communication between
WealthBuilder OS (Node.js) and the WealthBuilder Bridge (Python/FastAPI).

### Rules

1. **Neither side may change the API surface without first updating this document.**
2. **Every change requires a version bump** — patch for non-breaking, minor for
   additive, major for breaking.
3. **Breaking changes require a deprecation period** — the old and new endpoints
   coexist for at least one release cycle before the old one is removed.
4. **Fields marked `required` will always be present** in the response.  Clients
   must not depend on fields not listed here.
5. **Fields marked `optional` may be absent** — clients must handle missing fields
   gracefully.
6. **Error codes are stable** — once a code is published it is never renamed or
   removed; new codes may be added.

### Versioning scheme

```
MAJOR.MINOR.PATCH

MAJOR — breaking change (field removed, type changed, endpoint removed)
MINOR — additive change (new endpoint, new optional field added)
PATCH — non-breaking fix (typo in message, documentation correction)
```

The API version string (`v1`, `v2`, …) increments only on MAJOR changes.

---

## Table of contents

1. [Connection details](#1-connection-details)
2. [Authentication](#2-authentication)
3. [Standard response envelope](#3-standard-response-envelope)
4. [Standard error codes](#4-standard-error-codes)
5. [HTTP status codes used](#5-http-status-codes-used)
6. [Request headers](#6-request-headers)
7. [Response headers](#7-response-headers)
8. [Endpoints](#8-endpoints)
   - 8.1 [Health](#81-get-health)
   - 8.2 [Account — get info](#82-get-apiaccount)
   - 8.3 [Account — balance](#83-get-apiaccountbalance)
   - 8.4 [Account — margin](#84-get-apiaccountmargin)
   - 8.5 [Positions — list](#85-get-apipositions)
   - 8.6 [Positions — single](#86-get-apipositionsticket)
   - 8.7 [Symbols — list](#87-get-apisymbols)
   - 8.8 [Symbols — single](#88-get-apisymbolssymbol)
   - 8.9 [Market — tick](#89-get-apimarketsymboltick)
   - 8.10 [Market — rates](#810-get-apimarketsymbolrates)
   - 8.11 [Trade — open](#811-post-apitradeopen)
   - 8.12 [Trade — modify](#812-put-apitradenticketmodify)
   - 8.13 [Trade — close](#813-delete-apitradenticketclose)
   - 8.14 [History — deals](#814-get-apihistorydeals)
   - 8.15 [History — orders](#815-get-apihistoryorders)
9. [JSON schemas](#9-json-schemas)
10. [Changelog](#10-changelog)

---

## 1. Connection details

| Property | Value |
|----------|-------|
| Protocol | HTTP/1.1 |
| Base URL (development) | `http://localhost:8000` |
| Base URL (production) | TBD — Phase 2.2 |
| Content type | `application/json` (all requests and responses) |
| Character encoding | UTF-8 |
| Timeout | 30 seconds (configurable via `REQUEST_TIMEOUT`) |

All timestamps are **ISO-8601 strings in UTC**, e.g. `"2026-07-14T16:27:53.705016Z"`.

All monetary values are **IEEE 754 64-bit floats** represented as JSON numbers.

---

## 2. Authentication

### Scheme

Bearer token.  Every endpoint except `GET /health` requires the header:

```
Authorization: Bearer <token>
```

### Token source

The token is the value of the `AUTH_TOKEN` environment variable configured
on the bridge server.  WealthBuilder OS must read this value from its own
secure secret store and include it on every protected request.

### Exempt paths (no token required)

| Path | Reason |
|------|--------|
| `GET /health` | Operational monitoring — must be reachable without credentials |
| `GET /docs` | Swagger UI |
| `GET /redoc` | ReDoc UI |
| `GET /openapi.json` | OpenAPI schema |

### Authentication failures

A missing, malformed, or incorrect token produces:

```
HTTP/1.1 401 Unauthorized
Content-Type: application/json
X-Request-ID: <uuid>
```

```json
{
  "success": false,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": null,
  "error": {
    "code": "AUTHENTICATION_FAILED",
    "message": "Missing or malformed Authorization header. Expected: Authorization: Bearer <token>"
  }
}
```

---

## 3. Standard response envelope

**Every endpoint** returns this envelope.  No exceptions.

### Schema

```json
{
  "success":   "<boolean>  — true on success, false on any error",
  "requestId": "<string>   — UUID v4 echoing the X-Request-ID header",
  "timestamp": "<string>   — ISO-8601 UTC timestamp of response generation",
  "data":      "<object|null> — payload on success; null on error",
  "error":     "<object|null> — error detail on failure; null on success"
}
```

### Field rules

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `success` | boolean | Yes | `true` when `data` is populated; `false` when `error` is populated |
| `requestId` | string (UUID v4) | Yes | Matches `X-Request-ID` response header |
| `timestamp` | string (ISO-8601 UTC) | Yes | Server time at response generation |
| `data` | object or null | Yes | Present on success; `null` on error |
| `error` | object or null | Yes | Present on error; `null` on success |

Exactly one of `data` or `error` is non-null for any given response.

### Error object schema

```json
{
  "code":    "<string> — upper-snake-case error code (stable across versions)",
  "message": "<string> — human-readable description safe for logging"
}
```

### Success example

```json
{
  "success": true,
  "requestId": "a4a0bedf-4469-4bdf-bc23-f46c475e9a3d",
  "timestamp": "2026-07-14T16:28:53.659Z",
  "data": { "...": "..." },
  "error": null
}
```

### Error example

```json
{
  "success": false,
  "requestId": "b5b1cef0-5570-5ce5-bd34-557766551111",
  "timestamp": "2026-07-14T16:28:54.001Z",
  "data": null,
  "error": {
    "code": "AUTHENTICATION_FAILED",
    "message": "Invalid bearer token."
  }
}
```

---

## 4. Standard error codes

These codes appear in `error.code` and are **stable** — they will never be
renamed or removed.  New codes may be added in future versions.

| Code | HTTP status | Meaning |
|------|------------|---------|
| `AUTHENTICATION_FAILED` | 401 | Missing, malformed, or incorrect bearer token |
| `VALIDATION_ERROR` | 422 | Request input failed schema validation |
| `NOT_IMPLEMENTED` | 501 | Endpoint exists in the contract but is not yet implemented |
| `INTERNAL_ERROR` | 500 | Unexpected server-side failure |
| `CONFIGURATION_ERROR` | 500 | Server misconfiguration detected at runtime |

---

## 5. HTTP status codes used

| Status | Meaning in this API |
|--------|-------------------|
| `200 OK` | Request succeeded; `data` is populated |
| `401 Unauthorized` | Authentication failed |
| `422 Unprocessable Entity` | Request body or query parameter validation failed |
| `500 Internal Server Error` | Unexpected server failure |
| `501 Not Implemented` | Endpoint is declared but not yet implemented (Phase 2.1 stubs) |

No other status codes are used in Phase 2.1.  Phase 2.2 may add:

| Status | Expected use |
|--------|-------------|
| `404 Not Found` | Requested resource (ticket, symbol) does not exist |
| `409 Conflict` | Operation rejected due to broker-side state (e.g. market closed) |
| `503 Service Unavailable` | Bridge is not connected to the broker |

---

## 6. Request headers

### Required (protected endpoints)

| Header | Value | Example |
|--------|-------|---------|
| `Authorization` | `Bearer <token>` | `Bearer dev-local-token` |

### Optional

| Header | Value | Behaviour |
|--------|-------|-----------|
| `X-Request-ID` | UUID v4 | If provided, the bridge echoes it back rather than generating a new one.  Use this for distributed tracing. |
| `Content-Type` | `application/json` | Required on `POST` and `PUT` requests with a body |

---

## 7. Response headers

Every response includes:

| Header | Value | Example |
|--------|-------|---------|
| `X-Request-ID` | UUID v4 | `a4a0bedf-4469-4bdf-bc23-f46c475e9a3d` |
| `X-Process-Time-Ms` | Float (milliseconds) | `4.23` |
| `Content-Type` | `application/json` | `application/json` |

---

## 8. Endpoints

### 8.1 `GET /health`

**Purpose:** Returns the operational status of the bridge.  
**Authentication:** None.  
**Phase:** 2.1 — fully implemented.

#### Request

No parameters, headers, or body required.

#### Response — 200 OK

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "applicationName":    "<string>  — 'WealthBuilder Bridge'",
    "applicationVersion": "<string>  — semver, e.g. '2.1.0'",
    "apiVersion":         "<string>  — e.g. 'v1'",
    "environment":        "<string>  — 'development' | 'staging' | 'production'",
    "startupTime":        "<string>  — ISO-8601 UTC timestamp of server start",
    "uptimeSeconds":      "<number>  — seconds since startup, 3 decimal places",
    "bridgeStatus":       "<string>  — 'DISCONNECTED' | 'INITIALIZING' | 'READY' | 'SHUTTING_DOWN'"
  },
  "error": null
}
```

#### `bridgeStatus` values

| Value | Meaning |
|-------|---------|
| `DISCONNECTED` | Bridge has not started or has been stopped |
| `INITIALIZING` | Startup sequence is running |
| `READY` | Bridge is operational and accepting requests |
| `SHUTTING_DOWN` | Graceful shutdown in progress |

WealthBuilder OS should poll this endpoint and wait for `READY` before
sending any protected requests.

#### Example

```
GET /health HTTP/1.1
Host: localhost:8000
```

```json
{
  "success": true,
  "requestId": "a4a0bedf-4469-4bdf-bc23-f46c475e9a3d",
  "timestamp": "2026-07-14T16:28:53.659Z",
  "data": {
    "applicationName": "WealthBuilder Bridge",
    "applicationVersion": "2.1.0",
    "apiVersion": "v1",
    "environment": "development",
    "startupTime": "2026-07-14T16:27:53.705Z",
    "uptimeSeconds": 59.955,
    "bridgeStatus": "READY"
  },
  "error": null
}
```

---

### 8.2 `GET /api/account`

**Purpose:** Returns broker account metadata.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Request

No parameters or body.

#### Response — 200 OK (Phase 2.2+)

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "login":        "<integer> — broker account login number",
    "server":       "<string>  — broker server name",
    "name":         "<string>  — account holder name",
    "currency":     "<string>  — account base currency, e.g. 'USD'",
    "leverage":     "<integer> — leverage ratio, e.g. 100",
    "tradeAllowed": "<boolean> — whether trading is currently permitted"
  },
  "error": null
}
```

#### Response — 501 Not Implemented (Phase 2.1)

```json
{
  "success": false,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": null,
  "error": {
    "code": "NOT_IMPLEMENTED",
    "message": "This endpoint will be implemented in a future phase."
  }
}
```

---

### 8.3 `GET /api/account/balance`

**Purpose:** Returns real-time balance, equity, and profit.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Response — 200 OK (Phase 2.2+)

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "balance": "<number> — account balance",
    "equity":  "<number> — balance + floating profit/loss",
    "profit":  "<number> — sum of floating profit/loss on open positions"
  },
  "error": null
}
```

---

### 8.4 `GET /api/account/margin`

**Purpose:** Returns used margin, free margin, and margin level.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Response — 200 OK (Phase 2.2+)

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "margin":      "<number> — margin currently in use",
    "marginFree":  "<number> — margin available for new positions",
    "marginLevel": "<number> — equity / margin * 100 (percentage); null when margin is 0"
  },
  "error": null
}
```

---

### 8.5 `GET /api/positions`

**Purpose:** Returns all currently open positions.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Response — 200 OK (Phase 2.2+)

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "positions": [
      {
        "ticket":     "<integer> — unique broker position ticket",
        "symbol":     "<string>  — trading symbol, e.g. 'EURUSD'",
        "type":       "<string>  — 'BUY' | 'SELL'",
        "volume":     "<number>  — position size in lots",
        "openPrice":  "<number>  — price at which position was opened",
        "currentPrice": "<number> — current market price",
        "stopLoss":   "<number|null> — stop-loss price; null if not set",
        "takeProfit": "<number|null> — take-profit price; null if not set",
        "profit":     "<number>  — floating profit/loss in account currency",
        "swap":       "<number>  — accumulated swap charges",
        "commission": "<number>  — commission charged",
        "openTime":   "<string>  — ISO-8601 UTC timestamp of position open",
        "comment":    "<string>  — broker comment field"
      }
    ],
    "count": "<integer> — number of positions in the list"
  },
  "error": null
}
```

An empty portfolio returns `"positions": []` and `"count": 0`.

---

### 8.6 `GET /api/positions/{ticket}`

**Purpose:** Returns a single open position by broker ticket.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Path parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticket` | integer | Yes | Broker-assigned ticket number |

#### Response — 200 OK (Phase 2.2+)

`data` is a single position object with the same fields as the positions list item above.

#### Response — 404 Not Found (Phase 2.2+)

```json
{
  "success": false,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": null,
  "error": {
    "code": "NOT_FOUND",
    "message": "No open position found with ticket 12345."
  }
}
```

---

### 8.7 `GET /api/symbols`

**Purpose:** Returns all trading symbols available on the broker.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Response — 200 OK (Phase 2.2+)

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "symbols": [
      {
        "name":        "<string>  — symbol name, e.g. 'EURUSD'",
        "description": "<string>  — human-readable description",
        "currency":    "<string>  — profit currency",
        "category":    "<string>  — classification, e.g. 'Forex' | 'Metals' | 'Indices'"
      }
    ],
    "count": "<integer>"
  },
  "error": null
}
```

---

### 8.8 `GET /api/symbols/{symbol}`

**Purpose:** Returns the full specification for a named trading symbol.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Path parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Symbol name, e.g. `EURUSD` |

#### Response — 200 OK (Phase 2.2+)

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "name":             "<string>  — symbol name",
    "description":      "<string>  — human-readable description",
    "baseCurrency":     "<string>  — base currency",
    "profitCurrency":   "<string>  — profit currency",
    "digits":           "<integer> — decimal places in price",
    "contractSize":     "<number>  — units per lot",
    "minVolume":        "<number>  — minimum trade volume in lots",
    "maxVolume":        "<number>  — maximum trade volume in lots",
    "volumeStep":       "<number>  — volume increment step",
    "spread":           "<integer> — current spread in points",
    "tradeAllowed":     "<boolean> — whether trading this symbol is currently permitted"
  },
  "error": null
}
```

---

### 8.9 `GET /api/market/{symbol}/tick`

**Purpose:** Returns the latest bid/ask tick for a symbol.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Path parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Symbol name, e.g. `EURUSD` |

#### Response — 200 OK (Phase 2.2+)

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "symbol": "<string>  — symbol name",
    "time":   "<string>  — ISO-8601 UTC timestamp of tick",
    "bid":    "<number>  — current bid price",
    "ask":    "<number>  — current ask price",
    "last":   "<number>  — last trade price",
    "volume": "<number>  — tick volume"
  },
  "error": null
}
```

---

### 8.10 `GET /api/market/{symbol}/rates`

**Purpose:** Returns OHLCV candlestick data for a symbol and timeframe.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Path parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Symbol name, e.g. `EURUSD` |

#### Query parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `timeframe` | string | Yes | — | One of: `M1` `M5` `M15` `M30` `H1` `H4` `D1` `W1` `MN1` |
| `count` | integer | No | `100` | Number of bars to return (1–1000) |

#### Response — 200 OK (Phase 2.2+)

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "symbol":    "<string>",
    "timeframe": "<string>",
    "bars": [
      {
        "time":       "<string>  — ISO-8601 UTC open time of bar",
        "open":       "<number>  — open price",
        "high":       "<number>  — high price",
        "low":        "<number>  — low price",
        "close":      "<number>  — close price",
        "tickVolume": "<integer> — tick count during bar",
        "spread":     "<integer> — spread at bar open, in points",
        "realVolume": "<integer> — real traded volume (0 if unavailable)"
      }
    ],
    "count": "<integer> — number of bars returned"
  },
  "error": null
}
```

Bars are returned in **ascending chronological order** (oldest first).

---

### 8.11 `POST /api/trade/open`

**Purpose:** Sends a market or pending order to the broker.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Request body

```json
{
  "symbol":     "<string>  — required — symbol name, e.g. 'EURUSD'",
  "type":       "<string>  — required — 'BUY' | 'SELL'",
  "volume":     "<number>  — required — trade volume in lots",
  "price":      "<number|null> — required for pending orders; null for market orders",
  "stopLoss":   "<number|null> — optional — stop-loss price",
  "takeProfit": "<number|null> — optional — take-profit price",
  "comment":    "<string>  — optional — broker comment field (max 32 chars)"
}
```

#### Request body constraints

| Field | Constraint |
|-------|-----------|
| `symbol` | Must be a valid, tradeable symbol |
| `type` | Must be exactly `"BUY"` or `"SELL"` |
| `volume` | Must be within `[minVolume, maxVolume]` and a multiple of `volumeStep` |
| `comment` | Maximum 32 characters |

#### Response — 200 OK (Phase 2.2+)

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "ticket":         "<integer> — broker-assigned position ticket",
    "executionPrice": "<number>  — actual price at which order was filled",
    "executionTime":  "<string>  — ISO-8601 UTC timestamp of execution",
    "volume":         "<number>  — actual volume filled",
    "comment":        "<string>  — broker confirmation comment"
  },
  "error": null
}
```

---

### 8.12 `PUT /api/trade/{ticket}/modify`

**Purpose:** Modifies stop-loss and/or take-profit on an open position.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Path parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticket` | integer | Yes | Broker ticket of the position to modify |

#### Request body

```json
{
  "stopLoss":   "<number|null> — new stop-loss price; null to leave unchanged",
  "takeProfit": "<number|null> — new take-profit price; null to leave unchanged"
}
```

At least one of `stopLoss` or `takeProfit` must be non-null.

#### Response — 200 OK (Phase 2.2+)

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "ticket":     "<integer> — ticket of the modified position",
    "stopLoss":   "<number|null> — effective stop-loss after modification",
    "takeProfit": "<number|null> — effective take-profit after modification"
  },
  "error": null
}
```

---

### 8.13 `DELETE /api/trade/{ticket}/close`

**Purpose:** Closes an open position at the current market price.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Path parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticket` | integer | Yes | Broker ticket of the position to close |

#### Response — 200 OK (Phase 2.2+)

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "ticket":     "<integer> — ticket of the closed position",
    "closePrice": "<number>  — price at which position was closed",
    "closeTime":  "<string>  — ISO-8601 UTC timestamp of close",
    "profit":     "<number>  — realised profit/loss in account currency",
    "swap":       "<number>  — accumulated swap at time of close",
    "commission": "<number>  — commission at time of close"
  },
  "error": null
}
```

---

### 8.14 `GET /api/history/deals`

**Purpose:** Returns all closed deals within a date range.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Query parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dateFrom` | string (ISO-8601 UTC) | Yes | Start of query range |
| `dateTo` | string (ISO-8601 UTC) | Yes | End of query range |

#### Response — 200 OK (Phase 2.2+)

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "deals": [
      {
        "ticket":     "<integer> — unique deal ticket",
        "order":      "<integer> — originating order ticket",
        "symbol":     "<string>  — trading symbol",
        "type":       "<string>  — 'BUY' | 'SELL'",
        "entry":      "<string>  — 'IN' | 'OUT' | 'INOUT'",
        "volume":     "<number>  — deal volume in lots",
        "price":      "<number>  — deal execution price",
        "commission": "<number>  — commission charged",
        "swap":       "<number>  — swap applied",
        "profit":     "<number>  — realised profit/loss",
        "time":       "<string>  — ISO-8601 UTC timestamp of deal",
        "comment":    "<string>  — broker comment"
      }
    ],
    "count": "<integer>"
  },
  "error": null
}
```

---

### 8.15 `GET /api/history/orders`

**Purpose:** Returns all historical orders (filled and cancelled) within a date range.  
**Authentication:** Required.  
**Phase:** 2.2 — returns 501 in Phase 2.1.

#### Query parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dateFrom` | string (ISO-8601 UTC) | Yes | Start of query range |
| `dateTo` | string (ISO-8601 UTC) | Yes | End of query range |

#### Response — 200 OK (Phase 2.2+)

```json
{
  "success": true,
  "requestId": "<uuid>",
  "timestamp": "<iso8601-utc>",
  "data": {
    "orders": [
      {
        "ticket":     "<integer> — unique order ticket",
        "symbol":     "<string>  — trading symbol",
        "type":       "<string>  — 'BUY' | 'SELL' | 'BUY_LIMIT' | 'SELL_LIMIT' | 'BUY_STOP' | 'SELL_STOP'",
        "state":      "<string>  — 'FILLED' | 'CANCELLED' | 'PARTIAL'",
        "volume":     "<number>  — requested volume in lots",
        "volumeFilled": "<number> — actual filled volume",
        "price":      "<number>  — requested price (0 for market orders)",
        "stopLoss":   "<number|null>",
        "takeProfit": "<number|null>",
        "timeSetup":  "<string>  — ISO-8601 UTC order placement time",
        "timeDone":   "<string>  — ISO-8601 UTC order completion time",
        "comment":    "<string>  — broker comment"
      }
    ],
    "count": "<integer>"
  },
  "error": null
}
```

---

## 9. JSON schemas

### 9.1 BridgeResponse (envelope)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "BridgeResponse",
  "type": "object",
  "required": ["success", "requestId", "timestamp", "data", "error"],
  "additionalProperties": false,
  "properties": {
    "success":   { "type": "boolean" },
    "requestId": { "type": "string", "format": "uuid" },
    "timestamp": { "type": "string", "format": "date-time" },
    "data":      { "oneOf": [{ "type": "object" }, { "type": "null" }] },
    "error":     { "oneOf": [{ "$ref": "#/$defs/ErrorDetail" }, { "type": "null" }] }
  },
  "$defs": {
    "ErrorDetail": {
      "type": "object",
      "required": ["code", "message"],
      "additionalProperties": false,
      "properties": {
        "code":    { "type": "string", "pattern": "^[A-Z_]+$" },
        "message": { "type": "string" }
      }
    }
  }
}
```

### 9.2 TradeOpenRequest

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "TradeOpenRequest",
  "type": "object",
  "required": ["symbol", "type", "volume"],
  "additionalProperties": false,
  "properties": {
    "symbol":     { "type": "string", "minLength": 1 },
    "type":       { "type": "string", "enum": ["BUY", "SELL"] },
    "volume":     { "type": "number", "exclusiveMinimum": 0 },
    "price":      { "oneOf": [{ "type": "number", "exclusiveMinimum": 0 }, { "type": "null" }] },
    "stopLoss":   { "oneOf": [{ "type": "number", "exclusiveMinimum": 0 }, { "type": "null" }] },
    "takeProfit": { "oneOf": [{ "type": "number", "exclusiveMinimum": 0 }, { "type": "null" }] },
    "comment":    { "type": "string", "maxLength": 32 }
  }
}
```

### 9.3 TradeModifyRequest

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "TradeModifyRequest",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "stopLoss":   { "oneOf": [{ "type": "number", "exclusiveMinimum": 0 }, { "type": "null" }] },
    "takeProfit": { "oneOf": [{ "type": "number", "exclusiveMinimum": 0 }, { "type": "null" }] }
  },
  "minProperties": 1
}
```

### 9.4 RatesQuery

| Parameter | Type | Enum |
|-----------|------|------|
| `timeframe` | string | `M1` `M5` `M15` `M30` `H1` `H4` `D1` `W1` `MN1` |
| `count` | integer | 1–1000 |

### 9.5 HistoryQuery

| Parameter | Type | Format | Constraint |
|-----------|------|--------|-----------|
| `dateFrom` | string | ISO-8601 UTC | Must be before `dateTo` |
| `dateTo` | string | ISO-8601 UTC | Must be after `dateFrom` |

---

## 10. Changelog

| Version | Date | Type | Summary |
|---------|------|------|---------|
| 2.1.0 | 2026-07-14 | Initial | Contract established. Health endpoint functional. All other endpoints declared as 501 stubs. |

---

*This document is owned jointly by the WealthBuilder OS team (Node.js) and the WealthBuilder Bridge team (Python).  
Changes require sign-off from both sides before implementation begins.*
