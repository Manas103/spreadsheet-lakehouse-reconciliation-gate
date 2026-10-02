"""Idempotent, watermarked incremental load, uniform across all 9
sources: every source's rows for one load are tagged with the same
``cycle``/``Month``/``month`` value (the watermark), so "ingest this
cycle again with no new upstream data" is exactly "the watermark already
on file is >= this cycle's value", and that rerun inserts zero new rows.
Used by ``tests/test_ingest.py`` to prove the property for all 9 sources
against the real local PostgreSQL instance.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import pandas as pd

from reconcilegate import watermark as wm


@dataclass
class IngestResult:
    source_name: str
    rows_new: int
    no_op: bool
    content_hash: str
    watermark_value: float


def _content_signature(payload) -> str:
    if isinstance(payload, dict):
        parts = []
        for key in sorted(payload.keys()):
            parts.append(f"--{key}--")
            parts.append(_content_signature(payload[key]))
        raw = "\n".join(parts)
    elif isinstance(payload, pd.DataFrame):
        raw = payload.to_csv(index=False)
    elif isinstance(payload, list) and payload and isinstance(payload[0], str):
        raw = "\n".join(payload)
    elif isinstance(payload, list):
        raw = json.dumps(payload, sort_keys=True, default=str)
    else:
        raw = str(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _row_count(payload) -> int:
    if isinstance(payload, dict):
        return sum(_row_count(v) for v in payload.values())
    if isinstance(payload, pd.DataFrame):
        return len(payload)
    return len(payload)


def ingest_source(conn, source_name: str, payload, cycle_value: float) -> IngestResult:
    """``payload`` is whatever shape that source's canonical data takes
    for this one cycle (a dict of country DataFrames for excel, a flat
    DataFrame for csv/rest_api, a list of raw lines for fixed_width, a
    list of row dicts for the drifting-csv source's generator output).
    """
    last = wm.get_watermark(conn, source_name)
    content_hash = _content_signature(payload)

    if last is not None and cycle_value <= last:
        wm.record_ingest(conn, source_name, last, 0, content_hash, "no-op")
        return IngestResult(source_name, rows_new=0, no_op=True, content_hash=content_hash, watermark_value=last)

    rows_new = _row_count(payload)
    wm.record_ingest(conn, source_name, cycle_value, rows_new, content_hash, "ingested")
    return IngestResult(source_name, rows_new=rows_new, no_op=False, content_hash=content_hash, watermark_value=cycle_value)
