"""Build and atomically write Stage 4E.2.2 evidence documents."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import STAGE
from .alignment import EXPECTED_CHECKS, EXPECTED_LINKED_DEALS, EXPECTED_TRADES


SCHEMA_VERSION = "1.0.0"
ALGORITHM_VERSION = "canonical-broker-coordinate-v1"
OUTPUT_NAMES = {
    "alignment": "wealthbuilder_market_alignment_4e2_2_v1.json",
    "gap": "wealthbuilder_market_alignment_gap_4e2_2_v1.json",
    "report": "wealthbuilder_market_alignment_report_4e2_2_v1.json",
    "certification": "wealthbuilder_market_alignment_certification_4e2_2_v1.json",
}


def _authorization() -> dict[str, bool]:
    return {
        "technicalFeatureCalculation": False,
        "strategyFormulation": False,
        "paperTrading": False,
        "liveTrading": False,
        "orderPlacement": False,
    }


def build_documents(
    result: dict[str, Any],
    provenance: dict[str, Any],
    source_validation: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, dict[str, Any]]:
    counts = result["counts"]
    corpus_integrity = (
        counts["tradeRecords"] == EXPECTED_TRADES
        and counts["linkedDeals"] == EXPECTED_LINKED_DEALS
        and counts["checks"] == EXPECTED_CHECKS
    )
    timestamp_certified = corpus_integrity and counts["timestampAlignedChecks"] == EXPECTED_CHECKS
    price_evidence_complete = counts["strictBidOhlcPriceContainedChecks"] == EXPECTED_CHECKS
    price_review_required = not price_evidence_complete
    status = (
        "TIMESTAMP_ALIGNMENT_CERTIFIED_PRICE_EVIDENCE_REVIEW_REQUIRED"
        if timestamp_certified and price_review_required
        else "DATA_ALIGNMENT_CERTIFIED"
        if timestamp_certified
        else "DATA_ALIGNMENT_REVIEW_REQUIRED"
    )
    gates = {
        "corpusIntegrity": corpus_integrity,
        "dealLinkIntegrity": counts["linkedDeals"] == EXPECTED_LINKED_DEALS,
        "sourceIntegrity": len(source_validation) == 20,
        "canonicalTimestampIntegrity": set(result["observedOffsetMinutes"]).issubset({"0", "60"}),
        "timestampAlignment": timestamp_certified,
        "strictBidOhlcPriceContainment": price_evidence_complete,
        "priceEvidenceReviewRequired": price_review_required,
        "strategyFormulation": False,
        "paperTrading": False,
        "liveTrading": False,
        "orderPlacement": False,
    }
    common = {
        "schemaVersion": SCHEMA_VERSION,
        "algorithmVersion": ALGORITHM_VERSION,
        "stage": STAGE,
        "generatedAtUTC": generated_at or datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "status": status,
        "certificationScope": "Historical broker timestamp-to-OHLC temporal alignment only",
        "counts": counts,
        "observedOffsetMinutes": result["observedOffsetMinutes"],
        "gates": gates,
        "authorization": _authorization(),
        "provenance": provenance,
        "limitations": [
            "The brokerTime field is a timezone-naive broker wall clock; this stage does not claim it is UTC.",
            "Canonical timestamps project broker wall-clock components onto the MT5 OHLC epoch coordinate independently per linked deal; no global shift is applied.",
            "MT5 bar OHLC is bid-based. Execution-price containment is diagnostic until authoritative side-aware bid/ask or tick evidence and symbol point metadata are certified.",
            "No strategy, signal, recommendation, paper trade, order, or live deployment authorization is created.",
        ],
    }
    alignment = {
        **common,
        "records": result["records"],
        "checks": result["checks"],
        "sourceValidation": source_validation,
    }
    timestamp_failures = [item for item in result["checks"] if not item["timestampAligned"]]
    price_exceptions = [item for item in result["checks"] if not item["strictBidOhlcPriceContained"]]
    gap = {
        **common,
        "gapDefinition": "Unresolved temporal records/checks plus separately reported diagnostic price exceptions",
        "unresolvedRecords": result["unresolvedRecords"],
        "unresolvedTimestampChecks": timestamp_failures,
        "strictBidOhlcPriceDiagnosticExceptions": price_exceptions,
        "temporalGapCount": len(timestamp_failures),
        "priceDiagnosticExceptionCount": len(price_exceptions),
        "nextAction": "Acquire side-aware bid/ask or tick evidence before certifying execution-price containment.",
    }
    report = {
        **common,
        "summary": {
            "timestampAlignmentRate": counts["timestampAlignedChecks"] / counts["checks"] if counts["checks"] else 0,
            "strictBidOhlcPriceContainmentRate": counts["strictBidOhlcPriceContainedChecks"] / counts["checks"] if counts["checks"] else 0,
            "sourceFilesValidated": len(source_validation),
            "sourceBarCount": sum(item["barCount"] for item in source_validation.values()),
        },
        "sourceValidation": source_validation,
    }
    certification = {
        **common,
        "certified": timestamp_certified,
        "timestampAlignmentCertified": timestamp_certified,
        "executionPriceContainmentCertified": False,
        "certificationDecision": (
            "Temporal alignment certified; execution-price evidence remains explicitly uncertified."
            if timestamp_certified else "Temporal alignment is not certified."
        ),
    }
    return {"alignment": alignment, "gap": gap, "report": report, "certification": certification}


def write_documents(output_dir: Path, documents: dict[str, dict[str, Any]]) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[Path, Path]] = []
    try:
        for key, name in OUTPUT_NAMES.items():
            destination = output_dir / name
            if destination.exists():
                raise FileExistsError(f"refusing to overwrite immutable evidence: {destination}")
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", suffix=".partial", dir=output_dir)
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(documents[key], stream, indent=2, ensure_ascii=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            staged.append((temporary, destination))
        for temporary, destination in staged:
            temporary.replace(destination)
        return [destination for _, destination in staged]
    except Exception:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
        raise
