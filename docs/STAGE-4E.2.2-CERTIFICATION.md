# Stage 4E.2.2 — Canonical Timestamp Alignment

## Decision

Stage 4E.2.2 certifies the historical timestamp-to-OHLC temporal alignment of
the 85-record WealthBuilder closed-trade corpus.

- Closed trades: 85
- Linked entry/exit deals: 170
- MT5 OHLC source files: 20
- Source bars: 189,520
- Temporal checks: 680
- Temporally aligned checks: 680
- Unresolved temporal records: 0

The source `time` field and the timezone-naive `brokerTime` field have a
date-dependent relationship: 134 linked deals differ by 60 minutes and 36 by
zero minutes. The algorithm maps every ledger endpoint to its unique preserved
source deal and projects that deal's broker wall-clock components onto the MT5
OHLC epoch coordinate. It records both raw values and the observed offset. It
never applies a global timestamp shift and never claims that `brokerTime` is a
UTC timestamp.

## Price-evidence boundary

MT5 bar OHLC is bid-based. Only 581 of 680 execution prices fall strictly
inside the corresponding bid candle. That result does not invalidate temporal
alignment: buy-side executions, spread, tick sequence, and broker execution
conditions cannot be reconstructed authoritatively from bid-only bars.

Execution-price containment therefore remains explicitly uncertified until
side-aware bid/ask or tick evidence and authoritative symbol point/digit
metadata are acquired. Stage 4E.2.2 does not replace missing evidence with an
inferred spread tolerance.

## Safety and authorization

This stage is file-only and read-only. It performs no MT5 initialization,
network request, strategy formulation, technical-feature calculation, paper
trading, order placement, or live trading. All related authorization flags in
the evidence remain `false`.

## Run

Use `stage_4e2_2_canonical_timestamp_audit.py` with the closed-trade ledger,
raw reconciliation evidence, Stage 4E.2 OHLC directory, optional Stage 4E.2.1
requery manifest, and a new output directory. The writer refuses to overwrite
existing evidence files.

