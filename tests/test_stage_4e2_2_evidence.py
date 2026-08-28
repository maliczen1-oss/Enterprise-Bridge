import json

import pytest

from wealthbuilder_certification.evidence import OUTPUT_NAMES, build_documents, write_documents


def _result(timestamp_passed=680, price_passed=581):
    return {
        "counts": {
            "tradeRecords": 85, "linkedDeals": 170, "checks": 680,
            "timestampAlignedChecks": timestamp_passed,
            "timestampUnalignedChecks": 680 - timestamp_passed,
            "strictBidOhlcPriceContainedChecks": price_passed,
            "strictBidOhlcPriceExceptionChecks": 680 - price_passed,
            "unresolvedRecords": 0 if timestamp_passed == 680 else 1,
        },
        "observedOffsetMinutes": {"0": 36, "60": 134},
        "records": [], "checks": [], "unresolvedRecords": [],
    }


def test_temporal_certification_does_not_claim_price_certification():
    docs = build_documents(_result(), {}, {str(i): {"barCount": 1} for i in range(20)}, "2026-01-01T00:00:00Z")
    certification = docs["certification"]
    assert certification["timestampAlignmentCertified"] is True
    assert certification["executionPriceContainmentCertified"] is False
    assert certification["status"] == "TIMESTAMP_ALIGNMENT_CERTIFIED_PRICE_EVIDENCE_REVIEW_REQUIRED"
    assert not any(certification["authorization"].values())


def test_any_temporal_failure_prevents_certification():
    docs = build_documents(_result(timestamp_passed=679), {}, {str(i): {"barCount": 1} for i in range(20)})
    assert docs["certification"]["certified"] is False
    assert docs["certification"]["status"] == "DATA_ALIGNMENT_REVIEW_REQUIRED"


def test_atomic_writer_creates_all_versioned_outputs_and_refuses_overwrite(tmp_path):
    documents = build_documents(_result(), {}, {str(i): {"barCount": 1} for i in range(20)})
    paths = write_documents(tmp_path, documents)
    assert {path.name for path in paths} == set(OUTPUT_NAMES.values())
    assert all(json.loads(path.read_text())["stage"] == "4E.2.2" for path in paths)
    with pytest.raises(FileExistsError):
        write_documents(tmp_path, documents)
    assert not list(tmp_path.glob("*.partial"))
