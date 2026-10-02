"""Writes a batch (as produced by datagen.py) to real files on disk, one
per source format (4 .xlsx workbooks, 2 .csv system-of-record extracts,
1 .json vendor rate page dump, 1 fixed-width .txt vendor claims drop, 1
drifting-header .csv vendor directory drop), and reads each back through
the same parser a real ingestion job would use. Round-tripping through
the actual file format, not just passing DataFrames in memory, is what
makes every format's defects real rather than simulated in name only.

``vendor_rate_catalog`` is written as a flat JSON array here for speed in
the 40-defect/20-clean benchmark sweep rather than spun up as a live HTTP
server on every single load; the real cursor-paginated REST pull (and
the real paramiko SFTP pull for ``vendor_claims_extract``) are exercised
end to end in ``tests/test_apiserver_restclient.py`` and
``tests/test_sftp_io.py`` instead. See README "Honest framing" for why.
"""
from __future__ import annotations

import json
import os

import pandas as pd

from reconcilegate.contracts import CONTRACTS
from reconcilegate.drifting_csv import read_raw_csv, write_drifting_csv
from reconcilegate.excel_io import read_workbook, write_workbook
from reconcilegate.fixedwidth import read_raw_lines, write_fixed_width
from reconcilegate.layouts import LAYOUTS

EXCEL_SOURCES = ["shipment_log", "returns_register", "downtime_log", "complaint_tracker"]
CSV_SOURCES = ["erp_order_extract", "wms_shipment_extract"]


def write_batch(batch: dict, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for source in EXCEL_SOURCES:
        layout = LAYOUTS[source]
        overrides_for_source = batch.get("_header_overrides", {}).get(source, {})
        header_label_override = {
            country: list(reversed(layout.group_fields)) for country in overrides_for_source
        }
        path = os.path.join(out_dir, f"{source}.xlsx")
        write_workbook(path, batch[source], layout, header_label_override=header_label_override)
        paths[source] = path

    for source in CSV_SOURCES:
        path = os.path.join(out_dir, f"{source}.csv")
        batch[source].to_csv(path, index=False)
        paths[source] = path

    vrc_path = os.path.join(out_dir, "vendor_rate_catalog.json")
    with open(vrc_path, "w") as f:
        json.dump(batch["vendor_rate_catalog"], f)
    paths["vendor_rate_catalog"] = vrc_path

    claims_path = os.path.join(out_dir, "vendor_claims_extract.txt")
    corrupt = batch.get("_fixed_width_corrupt", {})
    write_fixed_width(claims_path, batch["vendor_claims_extract"], CONTRACTS["vendor_claims_extract"], corrupt=corrupt)
    paths["vendor_claims_extract"] = claims_path

    directory_payload = batch["vendor_directory_feed"]
    dir_path = os.path.join(out_dir, "vendor_directory_feed.csv")
    write_drifting_csv(dir_path, directory_payload["rows"], CONTRACTS["vendor_directory_feed"], directory_payload["header"])
    paths["vendor_directory_feed"] = dir_path

    return paths


def read_batch(paths: dict) -> dict:
    """Returns {source: <format-native parsed shape>}:
    excel -> {country: DataFrame}; csv/rest_api -> DataFrame;
    fixed_width -> list[str] raw lines; drifting_csv -> DataFrame with
    its original (possibly drifted) header, unmapped."""
    out = {}
    for source in EXCEL_SOURCES:
        sheets = read_workbook(paths[source])
        out[source] = {country: df for country, df in sheets.items()}
    for source in CSV_SOURCES:
        out[source] = pd.read_csv(paths[source])

    with open(paths["vendor_rate_catalog"]) as f:
        records = json.load(f)
    out["vendor_rate_catalog"] = pd.DataFrame(records, columns=CONTRACTS["vendor_rate_catalog"].expected_columns)

    out["vendor_claims_extract"] = read_raw_lines(paths["vendor_claims_extract"])

    out["vendor_directory_feed"] = read_raw_csv(paths["vendor_directory_feed"])

    return out
