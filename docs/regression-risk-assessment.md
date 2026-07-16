# Regression Risk Assessment — WealthBuilder Bridge Phase 2.1 → 2.2

## Risk summary

| Risk area | Level | Rationale |
|-----------|-------|-----------|
| Response envelope breakage | 🟢 Low | Single `BridgeResponse` model; one change propagates everywhere |
| Auth bypass regression | 🟡 Medium | `EXEMPT_PATHS` tuple is the single source of truth — easy to audit |
| Logging format regression | 🟢 Low | `_StructuredFormatter` is self-contained; no consumer depends on exact field order |
| Import cycle introduction | 🟡 Medium | Phase 2.2 broker SDK imports must be confined to service layer |
| `ConnectionManager` state corruption | 🟢 Low | State machine is sequential; no concurrent state mutations |
| Config validation regression | 🟢 Low | Validation runs at import time; any removal of required vars breaks startup |

---

## Detailed risk entries

### 1. Response envelope — LOW

**What could break:** Adding a field to `BridgeResponse` or changing an alias
(e.g. `requestId` → `request_id`) would change the wire format and break any
WealthBuilder OS client that parses the response.

**Mitigation:**
- `BridgeResponse` is in `core/models.py` — a single file with a single model.
- All builders (`success_response`, `error_response`, `not_implemented_response`)
  centralise construction; search for callers with `grep -r "success_response\|error_response"`.
- Alias changes require updating `model_config = {"populate_by_name": True}`.
- The 66-test suite validates envelope shape on every protected route.

**Phase 2.2 action:** Do not change `BridgeResponse` fields or aliases without
updating the WealthBuilder OS client contract and bumping the API version.

---

### 2. Authentication bypass — MEDIUM

**What could break:** Adding a new path to `EXEMPT_PATHS` by accident, or
routing a new protected endpoint through a prefix that matches an exempt path,
would expose data without authentication.

**Mitigation:**
- `EXEMPT_PATHS` is a single tuple in `middleware/auth.py` — one grep finds every exempt path.
- Phase 2.2 route additions must be tested with `test_protected_endpoint_returns_401_without_token`.
- The parametrised test list in `test_bridge.py::_PROTECTED_ROUTES` must be extended with every new endpoint added in Phase 2.2.

**Phase 2.2 action:** For every new route added, add its method and path to
`_PROTECTED_ROUTES` in `tests/test_bridge.py` before merging.

---

### 3. Import cycle introduction — MEDIUM

**What could break:** Phase 2.2 will import a broker SDK (e.g. `MetaTrader5`)
from service classes.  If the SDK is also imported at module level in `app.py`
or `config.py`, a circular dependency or import-time side effect (e.g. DLL
loading) could cause startup failures on non-Windows platforms.

**Mitigation:**
- Service layer imports must stay in service classes only.
- Broker SDK imports should be deferred inside method bodies if they have
  platform-specific requirements.
- Phase 2.2 should validate startup on the target platform (Windows) in CI.

---

### 4. `ConnectionManager` state machine — LOW

**What could break:** Phase 2.2 will add real broker connect / disconnect
calls inside `start()` / `stop()`.  If those calls raise and the state is
left in `INITIALIZING`, the health endpoint will not report READY.

**Mitigation:**
- Wrap broker calls in `try/except` inside `start()`.
- On failure, transition back to `DISCONNECTED` and raise `InternalException`.
- `app.py` lifespan propagates the exception, causing Uvicorn to refuse startup
  rather than serving a degraded instance.

---

### 5. Configuration regression — LOW

**What could break:** Removing a required variable from `_Settings.__init__`
without updating `.env.example` would cause silent deployment failures.

**Mitigation:**
- `.env.example` is the canonical list of required variables.
- `_require()` raises `ConfigurationException` at import time for any missing
  required variable — failures are immediate and descriptive.
- Any new Phase 2.2 required variable (e.g. `MT5_SERVER`, `MT5_LOGIN`) must
  be added to both `config.py` and `.env.example` atomically.

---

### 6. Middleware ordering — LOW

**What could break:** Inserting new middleware between `RequestIDMiddleware`
and `AuthenticationMiddleware` could cause auth decisions to run without a
request ID in the context, producing empty `requestId` fields in 401 responses.

**Mitigation:**
- Middleware is registered in `app.py` with a comment block explaining the
  required ordering.
- `RequestIDMiddleware` must always be the outermost layer.
- New middleware should be inserted between `TimingMiddleware` and
  `AccessLogMiddleware` unless it has a specific ordering requirement.

---

## Phase 2.2 pre-merge checklist

Before merging any Phase 2.2 branch:

- [ ] All 66 existing tests still pass with no modifications.
- [ ] Every new endpoint is added to `_PROTECTED_ROUTES` in `test_bridge.py`.
- [ ] `GET /health` still returns 200 with `bridgeStatus: READY`.
- [ ] No endpoint returns HTTP 500 under any test input.
- [ ] `EXEMPT_PATHS` has not changed (unless a new public endpoint was explicitly approved).
- [ ] `BridgeResponse` fields and aliases are unchanged.
- [ ] `.env.example` documents all new required variables.
- [ ] Broker SDK import is confined to the service layer.
