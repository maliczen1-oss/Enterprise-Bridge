"""
ATLAS CERTIFICATION HEADER
name=services/history_service.py
Version: 2.0.0

Change Log:
- Preserved the existing get_history() public interface.
- Preserved the existing top-level "deals" and "orders" response keys.
- Retained all broker fields returned by MT5Client instead of reducing records
  to a lossy seven-field representation.
- Added deterministic UTC timestamp normalization.
- Preserved broker-native symbols exactly as supplied by MetaApi/MT5.
- Added stable record identities for downstream idempotent learning ingestion.
- Added deterministic duplicate suppression within deals and orders.
- Added deterministic TOTAL limit handling across both record collections.
- Added deterministic ordering for reproducible downstream learning datasets.
- Added learning-ready metadata without embedding trading intelligence in the
  Enterprise Bridge.
- Added defensive validation and serialization of broker-native values.
- Added explicit connection-state and upstream-error awareness.
- Preserved backward compatibility with api/history.py and BridgeResponse.
- Avoided modification of the API layer, connection manager, or MT5 client.

Production Certification: Phase 4.0
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.connection_manager import manager as connection_manager

logger = logging.getLogger("bridge")


# ============================================================================
# Constants
# ============================================================================

_HISTORY_RECORD_TYPES = frozenset({"deal", "order"})

# Fields which are known to represent timestamps in MT5 / MetaApi responses.
# The service does not discard any original fields; it additionally normalizes
# recognised timestamp fields into JSON-safe UTC ISO-8601 strings.
_TIMESTAMP_FIELDS = frozenset(
    {
        "time",
        "time_done",
        "time_done_msc",
        "time_msc",
        "time_created",
        "time_updated",
        "create_time",
        "update_time",
        "open_time",
        "close_time",
        "entry_time",
        "exit_time",
        "expiration",
        "expiration_time",
        "broker_time",
    }
)

# Candidate identity fields are deliberately ordered from most specific to
# least specific. The actual broker record is retained unchanged apart from
# additive normalized metadata.
_DEAL_ID_FIELDS = (
    "dealId",
    "deal_id",
    "deal",
    "ticket",
    "id",
)

_ORDER_ID_FIELDS = (
    "orderId",
    "order_id",
    "order",
    "ticket",
    "id",
)

_POSITION_ID_FIELDS = (
    "positionId",
    "position_id",
    "position",
)

_SYMBOL_FIELDS = (
    "symbol",
)

_TIME_FIELDS = (
    "time",
    "time_done",
    "time_created",
    "time_updated",
    "open_time",
    "close_time",
)

# Fields useful to downstream learning. We do not invent values; the learning
# metadata simply records which contextual fields were actually available.
_LEARNING_CONTEXT_FIELDS = (
    "symbol",
    "type",
    "typeName",
    "direction",
    "entryType",
    "entry",
    "reason",
    "volume",
    "price",
    "profit",
    "commission",
    "swap",
    "fee",
    "comment",
    "positionId",
    "position_id",
    "orderId",
    "order_id",
    "dealId",
    "deal_id",
    "ticket",
    "time",
    "time_done",
    "time_created",
    "time_updated",
)


# ============================================================================
# Public compatibility helpers
# ============================================================================


def _safe_list(
    value: Optional[Iterable[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """
    Convert a connection-manager result into a list of dictionaries.

    The current ConnectionManager contract returns lists, but defensive
    normalization prevents malformed upstream data from breaking the API.
    """
    if not isinstance(value, list):
        return []

    result: List[Dict[str, Any]] = []

    for item in value:
        if isinstance(item, dict):
            result.append(dict(item))

    return result


# ============================================================================
# Generic normalization helpers
# ============================================================================


def _utc_datetime(value: Any) -> Optional[dt.datetime]:
    """
    Convert a supported timestamp representation to timezone-aware UTC.

    Supported values:
      - datetime
      - numeric Unix timestamps in seconds
      - numeric Unix timestamps in milliseconds
      - ISO-8601 strings

    Returns None when the value cannot be safely interpreted.

    The function is deliberately conservative because broker payloads can
    contain identifiers which happen to look numeric but are not timestamps.
    """
    if value is None:
        return None

    if isinstance(value, dt.datetime):
        result = value

        if result.tzinfo is None:
            # The API currently accepts naive datetimes. Preserve compatibility
            # by interpreting a naive broker/service datetime as UTC rather than
            # introducing local-machine timezone dependence.
            result = result.replace(tzinfo=dt.timezone.utc)

        return result.astimezone(dt.timezone.utc)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            numeric = float(value)

            if not math.isfinite(numeric):
                return None

            # MT5/MetaApi may expose either seconds or milliseconds.
            # Unix timestamps after year ~2001 exceed 1e9 seconds; values in
            # the trillions are therefore treated as milliseconds.
            if abs(numeric) >= 100_000_000_000:
                numeric /= 1000.0

            return dt.datetime.fromtimestamp(
                numeric,
                tz=dt.timezone.utc,
            )
        except (OverflowError, OSError, ValueError):
            return None

    if isinstance(value, str):
        candidate = value.strip()

        if not candidate:
            return None

        # Standard ISO-8601 UTC "Z".
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"

        try:
            parsed = dt.datetime.fromisoformat(candidate)

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)

            return parsed.astimezone(dt.timezone.utc)
        except ValueError:
            return None

    return None


def _iso_utc(value: Any) -> Optional[str]:
    """Return a normalized UTC ISO-8601 timestamp or None."""
    parsed = _utc_datetime(value)

    if parsed is None:
        return None

    return parsed.isoformat().replace("+00:00", "Z")


def _timestamp_value(
    record: Dict[str, Any],
) -> Optional[dt.datetime]:
    """
    Find the best available timestamp for deterministic ordering.

    Preference follows the record's execution lifecycle rather than assuming
    every broker record uses the same timestamp field.
    """
    for field in _TIME_FIELDS:
        if field not in record:
            continue

        parsed = _utc_datetime(record.get(field))

        if parsed is not None:
            return parsed

    return None


def _timestamp_sort_key(
    record: Dict[str, Any],
) -> Tuple[float, str]:
    """
    Deterministic descending timestamp key.

    Unknown timestamps are placed after known timestamps.
    """
    timestamp = _timestamp_value(record)

    if timestamp is None:
        return (float("-inf"), str(record.get("record_id", "")))

    return (
        timestamp.timestamp(),
        str(record.get("record_id", "")),
    )


def _json_safe(value: Any) -> Any:
    """
    Recursively convert broker-native values into JSON-safe values.

    This is additive/safety normalization only. It does not intentionally
    remove broker fields.
    """
    if value is None:
        return None

    if isinstance(value, dt.datetime):
        normalized = _iso_utc(value)
        return normalized if normalized is not None else str(value)

    if isinstance(value, dt.date):
        return value.isoformat()

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if math.isfinite(value):
            return value

        return None

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    # MetaApi/MT5 objects should normally already have been converted by
    # mt5_client.py. This fallback keeps the API JSON-safe if an unexpected
    # object reaches this layer.
    if hasattr(value, "_asdict"):
        try:
            return _json_safe(dict(value._asdict()))
        except Exception:
            pass

    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _canonical_identity_component(value: Any) -> str:
    """Convert an identity component into a stable comparable string."""
    if value is None:
        return ""

    if isinstance(value, float):
        if not math.isfinite(value):
            return ""

        return format(value, ".15g")

    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(
                _json_safe(value),
                sort_keys=True,
                separators=(",", ":"),
            )
        except Exception:
            return str(value)

    return str(value).strip()


# ============================================================================
# Stable identity
# ============================================================================


def _first_present(
    record: Dict[str, Any],
    fields: Iterable[str],
) -> Any:
    """Return the first non-empty field value from a record."""
    for field in fields:
        if field not in record:
            continue

        value = record.get(field)

        if value is None:
            continue

        if isinstance(value, str) and not value.strip():
            continue

        return value

    return None


def _stable_record_id(
    record: Dict[str, Any],
    record_type: str,
) -> str:
    """
    Generate a deterministic, non-secret record identity.

    Primary identity uses broker identifiers where available. A SHA-256
    fallback is used when a broker response lacks a unique identifier.

    The identity deliberately includes record_type because an order ticket and
    a deal ticket can legitimately occupy the same numeric namespace.
    """
    if record_type == "deal":
        primary_fields = _DEAL_ID_FIELDS
    else:
        primary_fields = _ORDER_ID_FIELDS

    primary = _first_present(record, primary_fields)

    position_id = _first_present(
        record,
        _POSITION_ID_FIELDS,
    )

    symbol = _first_present(
        record,
        _SYMBOL_FIELDS,
    )

    timestamp = _timestamp_value(record)

    if timestamp is not None:
        timestamp_component = timestamp.isoformat()
    else:
        timestamp_component = ""

    if primary is not None:
        identity_source = "|".join(
            [
                record_type,
                _canonical_identity_component(primary),
                _canonical_identity_component(position_id),
                _canonical_identity_component(symbol),
                timestamp_component,
            ]
        )
    else:
        # No explicit broker identifier exists. Build a deterministic digest
        # from the complete normalized record rather than generating a random
        # UUID. This makes repeated ingestion idempotent.
        canonical = _json_safe(record)

        try:
            canonical_payload = json.dumps(
                canonical,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
        except Exception:
            canonical_payload = repr(canonical)

        identity_source = "|".join(
            [
                record_type,
                canonical_payload,
            ]
        )

    digest = hashlib.sha256(
        identity_source.encode("utf-8")
    ).hexdigest()

    return f"{record_type}_{digest[:24]}"


# ============================================================================
# Record normalization
# ============================================================================


def _normalize_timestamp_fields(
    record: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Normalize recognized timestamp fields in-place on a copied record.

    Original field names are retained. Only their representation becomes
    JSON-safe and deterministic.
    """
    normalized = dict(record)

    for field in list(normalized.keys()):
        if field.lower() not in _TIMESTAMP_FIELDS:
            continue

        value = normalized.get(field)
        timestamp = _iso_utc(value)

        if timestamp is not None:
            normalized[field] = timestamp
        else:
            # Do not fabricate timestamps. Preserve the original value if it
            # cannot safely be interpreted.
            normalized[field] = _json_safe(value)

    return normalized


def _build_learning_metadata(
    record: Dict[str, Any],
    record_type: str,
) -> Dict[str, Any]:
    """
    Build additive metadata for downstream WealthBuilder ingestion.

    This is intentionally descriptive rather than predictive. The Enterprise
    Bridge reports broker facts; WealthBuilder/Jarvis performs the learning.
    """
    context: Dict[str, Any] = {}

    for field in _LEARNING_CONTEXT_FIELDS:
        if field in record and record.get(field) is not None:
            context[field] = _json_safe(record.get(field))

    timestamp = _timestamp_value(record)

    return {
        "recordType": record_type,
        "recordId": str(record.get("record_id", "")),
        "symbol": record.get("symbol"),
        "timestamp": (
            timestamp.isoformat().replace("+00:00", "Z")
            if timestamp is not None
            else None
        ),
        "availableContext": context,
    }


def _normalize_record(
    record: Dict[str, Any],
    record_type: str,
) -> Optional[Dict[str, Any]]:
    """
    Preserve a broker record while adding canonical metadata.

    No broker-native field is intentionally removed.
    """
    if not isinstance(record, dict):
        return None

    normalized = _normalize_timestamp_fields(record)

    # Normalize values recursively so BridgeResponse remains JSON-safe.
    normalized = _json_safe(normalized)

    if not isinstance(normalized, dict):
        return None

    # Preserve the exact broker-native symbol. We only strip surrounding
    # whitespace when the value is a string; we never alter suffixes/prefixes
    # such as EURUSD.mic or .DE30.mic.
    symbol = normalized.get("symbol")

    if isinstance(symbol, str):
        normalized["symbol"] = symbol.strip()

    normalized["record_type"] = record_type
    normalized["record_id"] = _stable_record_id(
        normalized,
        record_type,
    )

    # Additive learning metadata. No strategy interpretation occurs here.
    normalized["learning"] = _build_learning_metadata(
        normalized,
        record_type,
    )

    return normalized


# ============================================================================
# Deduplication
# ============================================================================


def _deduplicate_records(
    records: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Remove duplicate records deterministically.

    Deduplication is performed by stable record_id. This is intentionally
    applied separately to deals and orders because an order and a deal may
    legitimately share identifiers such as ticket numbers.
    """
    unique: Dict[str, Dict[str, Any]] = {}

    for record in records:
        if not isinstance(record, dict):
            continue

        record_id = str(record.get("record_id", "")).strip()

        if not record_id:
            # This should never happen after normalization, but malformed
            # records are skipped rather than generating a random identity.
            continue

        if record_id not in unique:
            unique[record_id] = record

    return list(unique.values())


# ============================================================================
# Deterministic ordering
# ============================================================================


def _sort_records(
    records: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Sort newest-first with stable record-ID tie breaking.

    A deterministic order is essential for reproducible learning ingestion and
    pagination.
    """
    return sorted(
        records,
        key=lambda item: (
            -_timestamp_sort_key(item)[0],
            str(item.get("record_id", "")),
        ),
    )


def _apply_total_limit(
    deals: List[Dict[str, Any]],
    orders: List[Dict[str, Any]],
    limit: Optional[int],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Apply a deterministic TOTAL limit across deals + orders.

    The existing implementation applied the limit independently to each
    collection. This replacement interprets `limit` as the maximum number of
    history records returned by the endpoint as a whole.

    Records are selected newest-first. The original collection membership is
    retained.
    """
    if limit is None:
        return deals, orders

    if not isinstance(limit, int) or isinstance(limit, bool):
        return deals, orders

    if limit <= 0:
        return [], []

    combined: List[Tuple[str, Dict[str, Any]]] = []

    for record in deals:
        combined.append(("deal", record))

    for record in orders:
        combined.append(("order", record))

    combined.sort(
        key=lambda item: (
            -_timestamp_sort_key(item[1])[0],
            str(item[1].get("record_id", "")),
            item[0],
        )
    )

    selected = combined[:limit]

    selected_deal_ids = {
        str(record.get("record_id"))
        for record_type, record in selected
        if record_type == "deal"
    }

    selected_order_ids = {
        str(record.get("record_id"))
        for record_type, record in selected
        if record_type == "order"
    }

    return (
        [
            record
            for record in deals
            if str(record.get("record_id")) in selected_deal_ids
        ],
        [
            record
            for record in orders
            if str(record.get("record_id")) in selected_order_ids
        ],
    )


# ============================================================================
# Upstream status handling
# ============================================================================


def _connection_is_ready() -> bool:
    """Return True only when the connection manager reports a ready state."""
    try:
        state = connection_manager.get_state()

        return state == "CONNECTED"
    except Exception:
        logger.exception(
            "Unable to determine connection-manager state during history "
            "request."
        )

        return False


def _last_connection_error() -> Optional[Dict[str, Any]]:
    """Read the connection manager's current diagnostic error safely."""
    try:
        error = connection_manager.get_last_error()

        return (
            dict(error)
            if isinstance(error, dict)
            else None
        )
    except Exception:
        logger.debug(
            "Unable to read connection-manager last error.",
            exc_info=True,
        )

        return None


def _history_error_changed(
    before: Optional[Dict[str, Any]],
    after: Optional[Dict[str, Any]],
    expected_codes: Iterable[str],
) -> bool:
    """
    Detect a history-specific upstream failure recorded by ConnectionManager.

    ConnectionManager currently returns [] when an MT5/MetaApi history call
    fails. This helper prevents those failures from being silently interpreted
    as legitimate empty history when the manager has recorded a new
    history-specific error.
    """
    if not isinstance(after, dict):
        return False

    after_code = after.get("code")

    if after_code not in set(expected_codes):
        return False

    before_timestamp = (
        before.get("timestamp")
        if isinstance(before, dict)
        else None
    )

    after_timestamp = after.get("timestamp")

    if before_timestamp is None:
        return True

    if after_timestamp is None:
        return True

    return after_timestamp != before_timestamp


# ============================================================================
# Public service API
# ============================================================================


def get_history(
    from_dt: dt.datetime,
    to_dt: dt.datetime,
    ticket: Optional[int] = None,
    symbol: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return normalized historical deals and orders.

    Public interface preserved:

        get_history(
            from_dt,
            to_dt,
            ticket=None,
            symbol=None,
            limit=None,
        )

    Response contract preserved:

        {
            "deals": [...],
            "orders": [...],
        }

    Behaviour:
      - Broker-native symbols are preserved exactly.
      - Broker fields are retained rather than reduced to a minimal subset.
      - Recognized timestamps are normalized to UTC ISO-8601 strings.
      - Records receive deterministic stable IDs.
      - Duplicate records are suppressed within each collection.
      - `limit` is a deterministic TOTAL record limit across deals + orders.
      - Empty history is returned as valid empty collections.
      - Connection/upstream failures are logged and surfaced as service-level
        exceptions so the API layer can retain its existing error envelope.
      - Learning metadata is additive and contains facts only; it does not
        make trading decisions.
    """
    logger.info(
        (
            "History request from=%s to=%s ticket=%s symbol=%s limit=%s"
        ),
        from_dt.isoformat() if isinstance(from_dt, dt.datetime) else from_dt,
        to_dt.isoformat() if isinstance(to_dt, dt.datetime) else to_dt,
        ticket,
        symbol,
        limit,
    )

    # ----------------------------------------------------------------------
    # Input validation
    # ----------------------------------------------------------------------

    if not isinstance(from_dt, dt.datetime):
        raise ValueError("from_dt must be a datetime")

    if not isinstance(to_dt, dt.datetime):
        raise ValueError("to_dt must be a datetime")

    normalized_from = _utc_datetime(from_dt)
    normalized_to = _utc_datetime(to_dt)

    if normalized_from is None or normalized_to is None:
        raise ValueError("History timestamps must be valid datetimes")

    if normalized_from > normalized_to:
        raise ValueError("from_dt must not be later than to_dt")

    if ticket is not None:
        if not isinstance(ticket, int) or isinstance(ticket, bool):
            raise ValueError("ticket must be an integer")

        if ticket <= 0:
            raise ValueError("ticket must be greater than zero")

    normalized_symbol: Optional[str] = None

    if symbol is not None:
        if not isinstance(symbol, str):
            raise ValueError("symbol must be a string")

        normalized_symbol = symbol.strip()

        if not normalized_symbol:
            raise ValueError("symbol must not be empty")

    if limit is not None:
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("limit must be an integer")

        if limit <= 0:
            # Preserve a predictable service contract. A positive limit is the
            # only meaningful bounded-history request.
            return {
                "deals": [],
                "orders": [],
            }

    # ----------------------------------------------------------------------
    # Connection state
    # ----------------------------------------------------------------------

    if not _connection_is_ready():
        logger.warning(
            (
                "History request rejected because bridge is not connected "
                "- symbol=%s ticket=%s"
            ),
            normalized_symbol,
            ticket,
        )

        raise RuntimeError(
            "Bridge is not connected to MT5"
        )

    # ----------------------------------------------------------------------
    # Fetch deals
    # ----------------------------------------------------------------------

    deals_before_error = _last_connection_error()
    deals_fetch_failed = False

    try:
        raw_deals = connection_manager.fetch_history_deals(
            normalized_from,
            normalized_to,
            ticket=ticket,
            symbol=normalized_symbol,
        )
    except Exception as exc:
        deals_fetch_failed = True
        raw_deals = []

        logger.exception(
            (
                "Failed to fetch history deals "
                "- symbol=%s ticket=%s"
            ),
            normalized_symbol,
            ticket,
        )

        deals_after_error = _last_connection_error()

        raise RuntimeError(
            "Unable to fetch historical deals"
        ) from exc

    deals_after_error = _last_connection_error()

    if _history_error_changed(
        deals_before_error,
        deals_after_error,
        {
            "FETCH_HISTORY_DEALS_FAILED",
        },
    ):
        deals_fetch_failed = True

    if deals_fetch_failed:
        raise RuntimeError(
            "Unable to fetch historical deals"
        )

    deals = _safe_list(raw_deals)

    # ----------------------------------------------------------------------
    # Fetch orders
    # ----------------------------------------------------------------------

    orders_before_error = _last_connection_error()
    orders_fetch_failed = False

    try:
        raw_orders = connection_manager.fetch_history_orders(
            normalized_from,
            normalized_to,
            ticket=ticket,
            symbol=normalized_symbol,
        )
    except Exception as exc:
        orders_fetch_failed = True
        raw_orders = []

        logger.exception(
            (
                "Failed to fetch history orders "
                "- symbol=%s ticket=%s"
            ),
            normalized_symbol,
            ticket,
        )

        raise RuntimeError(
            "Unable to fetch historical orders"
        ) from exc

    orders_after_error = _last_connection_error()

    if _history_error_changed(
        orders_before_error,
        orders_after_error,
        {
            "FETCH_HISTORY_ORDERS_FAILED",
        },
    ):
        orders_fetch_failed = True

    if orders_fetch_failed:
        raise RuntimeError(
            "Unable to fetch historical orders"
        )

    orders = _safe_list(raw_orders)

    # ----------------------------------------------------------------------
    # Normalize
    # ----------------------------------------------------------------------

    normalized_deals: List[Dict[str, Any]] = []

    for deal in deals:
        normalized = _normalize_record(
            deal,
            "deal",
        )

        if normalized is not None:
            normalized_deals.append(normalized)

    normalized_orders: List[Dict[str, Any]] = []

    for order in orders:
        normalized = _normalize_record(
            order,
            "order",
        )

        if normalized is not None:
            normalized_orders.append(normalized)

    # ----------------------------------------------------------------------
    # Deduplicate
    # ----------------------------------------------------------------------

    normalized_deals = _deduplicate_records(
        normalized_deals,
    )

    normalized_orders = _deduplicate_records(
        normalized_orders,
    )

    # ----------------------------------------------------------------------
    # Deterministic ordering
    # ----------------------------------------------------------------------

    normalized_deals = _sort_records(
        normalized_deals,
    )

    normalized_orders = _sort_records(
        normalized_orders,
    )

    # ----------------------------------------------------------------------
    # Deterministic TOTAL limit
    # ----------------------------------------------------------------------

    normalized_deals, normalized_orders = _apply_total_limit(
        normalized_deals,
        normalized_orders,
        limit,
    )

    # Re-sort after limiting to guarantee the returned collections themselves
    # are deterministic.
    normalized_deals = _sort_records(
        normalized_deals,
    )

    normalized_orders = _sort_records(
        normalized_orders,
    )

    # ----------------------------------------------------------------------
    # Observability
    # ----------------------------------------------------------------------

    total_records = (
        len(normalized_deals)
        + len(normalized_orders)
    )

    logger.info(
        (
            "History request completed "
            "deals=%d orders=%d total=%d symbol=%s ticket=%s limit=%s"
        ),
        len(normalized_deals),
        len(normalized_orders),
        total_records,
        normalized_symbol,
        ticket,
        limit,
    )

    if total_records == 0:
        logger.info(
            (
                "History request returned empty history "
                "- symbol=%s ticket=%s"
            ),
            normalized_symbol,
            ticket,
        )

    # ----------------------------------------------------------------------
    # Backward-compatible response
    # ----------------------------------------------------------------------

    return {
        "deals": normalized_deals,
        "orders": normalized_orders,
    }
