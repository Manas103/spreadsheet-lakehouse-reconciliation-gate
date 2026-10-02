"""Read/write/validate for ``vendor_directory_feed``, the source whose
successive drops genuinely drift: a column gets renamed to a contract-
declared alias, columns get reordered, and an optional column is
sometimes appended. Ingestion maps columns by declared name (or alias),
never by position; a required field whose name and every declared alias
are both absent from a drop's header is ``csv_header_drift``, the one
kind of drift this contract does not tolerate.

Three tolerated header shapes model three real drops of the same feed
over time (``VARIANT_HEADERS``), and three broken shapes model the
``csv_header_drift`` defect's three flavors (``BROKEN_VARIANT_HEADERS``):
a required column missing outright, or renamed to something that is not
a declared alias (indistinguishable, from the ingestion's point of view,
from "missing": the declared name never appears).
"""
from __future__ import annotations

import csv

import pandas as pd

from reconcilegate.contracts import SourceContract
from reconcilegate.validate import FailingCheck, _duplicate_key_checks, _field_checks

VARIANT_HEADERS = {
    "v1_original": ["vendor_id", "vendor_name", "tax_id", "status", "cycle"],
    "v2_renamed_reordered": ["vendor_name", "vendor_id", "tin", "cycle", "status"],
    "v3_with_region": ["vendor_id", "vendor_name", "tin", "status", "cycle", "region"],
}

BROKEN_VARIANT_HEADERS = {
    "missing_required_tax_id": ["vendor_id", "vendor_name", "status", "cycle"],
    "missing_required_vendor_name": ["vendor_id", "tax_id", "status", "cycle"],
    "unrecognized_rename_tax_id": ["vendor_id", "vendor_name", "fed_tax_number", "status", "cycle"],
}


def _field_for_header_name(name: str, contract: SourceContract):
    for fspec in contract.fields:
        if fspec.name == name or name in fspec.aliases:
            return fspec
    return None


def write_drifting_csv(path: str, rows: list, contract: SourceContract, header: list) -> None:
    """``rows``: list of dicts keyed by canonical field name. ``header``:
    the actual column names/order this drop's file will have on disk,
    one of VARIANT_HEADERS / BROKEN_VARIANT_HEADERS (or any list of
    names/aliases); a header entry resolves back to the canonical field
    it should pull its value from.
    """
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            out = []
            for h in header:
                fspec = _field_for_header_name(h, contract)
                out.append(row.get(fspec.name, "") if fspec is not None else "")
            writer.writerow(out)


def read_raw_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])


def map_to_canonical(df_raw: pd.DataFrame, contract: SourceContract) -> tuple:
    """Maps ``df_raw``'s actual (possibly drifted) header to canonical
    field names via the contract's declared name/alias list. Returns
    (canonical_df, missing_required_field_names)."""
    colmap = {}
    for col in df_raw.columns:
        fspec = _field_for_header_name(col, contract)
        if fspec is not None:
            colmap[col] = fspec.name

    found = set(colmap.values())
    canonical = pd.DataFrame(index=df_raw.index)
    missing_required = []
    for fspec in contract.fields:
        if fspec.name in found:
            raw_col = next(c for c, name in colmap.items() if name == fspec.name)
            canonical[fspec.name] = df_raw[raw_col]
        elif fspec.required:
            missing_required.append(fspec.name)
        # an absent optional field is simply not added to canonical; its
        # own nullability is irrelevant since the column isn't there.

    ordered_cols = [c for c in contract.expected_columns if c in canonical.columns]
    canonical = canonical[ordered_cols]
    return canonical, missing_required


def validate_drifting_csv_source(df_raw: pd.DataFrame, contract: SourceContract) -> list:
    canonical, missing_required = map_to_canonical(df_raw, contract)
    failing = []
    for name in missing_required:
        failing.append(
            FailingCheck(
                "csv_header_drift",
                contract.source_name,
                f"required field {name!r} (or a declared alias) not found in header {list(df_raw.columns)}",
            )
        )
    if missing_required:
        return failing  # column identity is unreliable past this point

    failing.extend(_field_checks(canonical, contract))
    failing.extend(_duplicate_key_checks(canonical, contract))
    return failing
