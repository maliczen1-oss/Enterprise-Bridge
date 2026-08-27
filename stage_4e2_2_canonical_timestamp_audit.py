"""Run the offline, read-only Stage 4E.2.2 canonical timestamp audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from wealthbuilder_certification.alignment import align, flatten_raw_records, ledger_records
from wealthbuilder_certification.evidence import build_documents, write_documents
from wealthbuilder_certification.ohlc import load_json, load_sources, sha256


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--raw-deals", required=True, type=Path)
    parser.add_argument("--ohlc-dir", required=True, type=Path)
    parser.add_argument("--requery-manifest", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--generated-at", help="Fixed ISO timestamp for reproducibility tests")
    return parser.parse_args()


def artifact(path: Path, role: str) -> dict[str, Any]:
    return {"role": role, "file": path.name, "sha256": sha256(path), "byteSize": path.stat().st_size}


def requery_provenance(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = load_json(path)
    if payload.get("tradingOperationsPerformed") is not False or payload.get("errors") != []:
        raise ValueError("4E.2.1 requery manifest did not record a clean read-only run")
    outputs = []
    for item in payload.get("outputs", []):
        source = Path(item["file"])
        if not source.is_file():
            raise ValueError(f"requery evidence file is missing: {source.name}")
        outputs.append(artifact(source, f"4E.2.1 {item.get('symbol')} {item.get('timeframe')} requery"))
    return {
        **artifact(path, "4E.2.1 targeted MT5 requery manifest"),
        "brokerServer": payload.get("brokerServer"),
        "requestedWindow": payload.get("requestedWindow"),
        "outputs": outputs,
    }


def main() -> int:
    args = parse_args()
    ledger = ledger_records(load_json(args.ledger))
    raw_records = flatten_raw_records(load_json(args.raw_deals))
    symbols = {item.get("Symbol") for item in ledger}
    if None in symbols or not all(isinstance(item, str) and item for item in symbols):
        raise ValueError("ledger contains a missing or invalid symbol")
    sources, source_validation, ohlc_provenance = load_sources(args.ohlc_dir, symbols)
    result = align(ledger, raw_records, sources)
    provenance = {
        "inputs": [artifact(args.ledger, "closed-trade ledger"), artifact(args.raw_deals, "raw linked deal evidence")],
        "ohlc": ohlc_provenance,
        "targetedRequery": requery_provenance(args.requery_manifest),
    }
    documents = build_documents(result, provenance, source_validation, args.generated_at)
    paths = write_documents(args.output_dir, documents)
    certification = documents["certification"]
    print(json.dumps({
        "stage": certification["stage"],
        "status": certification["status"],
        "timestampAlignmentCertified": certification["timestampAlignmentCertified"],
        "executionPriceContainmentCertified": certification["executionPriceContainmentCertified"],
        "counts": certification["counts"],
        "outputs": [str(path) for path in paths],
    }))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
