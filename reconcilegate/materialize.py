"""Writes a batch (as produced by datagen.py) to real files on disk (4
.xlsx workbooks, 2 .csv extracts) and reads them back through the same
parser a real ingestion job would use. Round-tripping through the actual
file format, not just passing DataFrames in memory, is what makes the
merged-header and per-country-tab defects real rather than simulated in
name only.
"""
from __future__ import annotations

import os

import pandas as pd

from reconcilegate.excel_io import read_workbook, write_workbook
from reconcilegate.layouts import LAYOUTS


def write_batch(batch: dict, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for source in ["shipment_log", "returns_register", "downtime_log", "complaint_tracker"]:
        layout = LAYOUTS[source]
        overrides_for_source = batch.get("_header_overrides", {}).get(source, {})
        header_label_override = {
            country: list(reversed(layout.group_fields)) for country in overrides_for_source
        }
        path = os.path.join(out_dir, f"{source}.xlsx")
        write_workbook(path, batch[source], layout, header_label_override=header_label_override)
        paths[source] = path

    for source in ["erp_order_extract", "wms_shipment_extract"]:
        path = os.path.join(out_dir, f"{source}.csv")
        batch[source].to_csv(path, index=False)
        paths[source] = path

    return paths


def read_batch(paths: dict) -> dict:
    """Returns {source: DataFrame}. Excel sources' per-country sheets are
    concatenated into one DataFrame (the Plant column already carries the
    country, same as a real ingestion job unioning per-tab reads)."""
    out = {}
    for source in ["shipment_log", "returns_register", "downtime_log", "complaint_tracker"]:
        sheets = read_workbook(paths[source])
        out[source] = {country: df for country, df in sheets.items()}
    for source in ["erp_order_extract", "wms_shipment_extract"]:
        out[source] = pd.read_csv(paths[source])
    return out
