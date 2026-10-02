"""Runs a source's declarative contract (contracts.py) against parsed
data (read back through excel_io.py / fixedwidth.py / drifting_csv.py /
pandas), returning a list of named failing checks. Nothing here is
source-specific `if` logic; every rule comes out of the contract object
passed in. The field-level checks (null, type, range, unit, duplicate
key) are shared helper functions used by every format's validator
(``validate_sheet`` for excel, ``validate_flat_source`` for csv/rest_api,
and ``fixedwidth.validate_fixed_width_source`` /
``drifting_csv.validate_drifting_csv_source`` for the 2 new formats);
only how a format discovers its columns (merged-header reconstruction,
plain CSV header, fixed byte offsets, or name-or-alias matching) differs
between them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from reconcilegate.config import UNIT_CONVERSION
from reconcilegate.contracts import SourceContract


@dataclass
class FailingCheck:
    check: str
    source: str
    detail: str

    def __str__(self) -> str:
        return f"{self.check}:{self.source}:{self.detail}"


def _is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _field_checks(df: pd.DataFrame, contract: SourceContract, country: str | None = None) -> list:
    """Null, type and (unit-aware) range checks for every declared field
    present in ``df``. A field absent from ``df`` entirely is not this
    function's concern, that is a column-discovery problem the caller
    (merged-header alignment, drift tolerance, fixed-width offsets) has
    already turned into its own named failing check before this runs.
    """
    failing = []
    prefix = f"{country} " if country is not None else ""

    # The field immediately before unit_field is denominated in whatever
    # unit that row's unit column names, not necessarily the canonical
    # unit its min_value/max_value were written against; convert before
    # range-checking it, or a valid mL row (e.g. 60 L = 60,000 mL) reads
    # as wildly out of range against an L-scale limit. See README
    # Findings for the run that surfaced this.
    unit_converted_field = contract.fields[-2].name if contract.unit_field else None
    factors = UNIT_CONVERSION.get(contract.source_name, {}).get("factors", {})

    for fspec in contract.fields:
        if fspec.name not in df.columns:
            continue
        col = df[fspec.name]
        for row_idx, value in col.items():
            if _is_missing(value):
                if not fspec.nullable:
                    failing.append(
                        FailingCheck(
                            "null_in_required_field",
                            contract.source_name,
                            f"{prefix}row {row_idx}: {fspec.name} is null",
                        )
                    )
                continue
            if fspec.dtype in ("int", "float"):
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    failing.append(
                        FailingCheck(
                            "type_mismatch",
                            contract.source_name,
                            f"{prefix}row {row_idx}: {fspec.name}={value!r} is not numeric",
                        )
                    )
                    continue
                range_check_value = numeric
                if fspec.name == unit_converted_field and contract.unit_field in df.columns:
                    row_unit = df.loc[row_idx, contract.unit_field]
                    if row_unit in factors:
                        range_check_value = numeric * factors[row_unit]
                if fspec.min_value is not None and range_check_value < fspec.min_value:
                    failing.append(
                        FailingCheck(
                            "out_of_range_value",
                            contract.source_name,
                            f"{prefix}row {row_idx}: {fspec.name}={numeric} < {fspec.min_value}",
                        )
                    )
                if fspec.max_value is not None and range_check_value > fspec.max_value:
                    failing.append(
                        FailingCheck(
                            "out_of_range_value",
                            contract.source_name,
                            f"{prefix}row {row_idx}: {fspec.name}={numeric} > {fspec.max_value}",
                        )
                    )
    return failing


def _unit_checks(df: pd.DataFrame, contract: SourceContract, country: str | None = None) -> list:
    failing = []
    prefix = f"{country} " if country is not None else ""
    if contract.unit_field is not None and contract.unit_field in df.columns:
        valid_units = set(UNIT_CONVERSION[contract.source_name]["factors"].keys())
        bad = df[~df[contract.unit_field].isin(valid_units)]
        for row_idx in bad.index:
            failing.append(
                FailingCheck(
                    "unexpected_unit_value",
                    contract.source_name,
                    f"{prefix}row {row_idx}: unit={df.loc[row_idx, contract.unit_field]!r} not in {sorted(valid_units)}",
                )
            )
    return failing


def _duplicate_key_checks(df: pd.DataFrame, contract: SourceContract, country: str | None = None) -> list:
    failing = []
    prefix = f"{country} " if country is not None else ""
    natural_key = contract.natural_key
    if natural_key and all(k in df.columns for k in natural_key):
        dup_mask = df.duplicated(subset=natural_key, keep=False)
        for row_idx in df[dup_mask].index:
            key_val = tuple(df.loc[row_idx, k] for k in natural_key)
            failing.append(
                FailingCheck(
                    "duplicate_natural_key",
                    contract.source_name,
                    f"{prefix}row {row_idx}: key {key_val} duplicated",
                )
            )
    return failing


def validate_sheet(df: pd.DataFrame, contract: SourceContract, country: str) -> list:
    """Assumes the tab exists (missing_required_tab is checked one level up)."""
    actual_columns = list(df.columns)
    if actual_columns != contract.expected_columns:
        return [
            FailingCheck(
                "merged_header_misaligned",
                contract.source_name,
                f"{country}: expected {contract.expected_columns}, got {actual_columns}",
            )
        ]  # column meaning is unreliable past this point

    failing = []
    failing.extend(_field_checks(df, contract, country))
    failing.extend(_unit_checks(df, contract, country))
    failing.extend(_duplicate_key_checks(df, contract, country))
    return failing


def validate_excel_source(sheets: dict, contract: SourceContract) -> list:
    failing = []
    missing_tabs = [c for c in contract.expected_countries if c not in sheets]
    for tab in missing_tabs:
        failing.append(FailingCheck("missing_required_tab", contract.source_name, tab))

    for country, df in sheets.items():
        if country not in contract.expected_countries:
            continue
        failing.extend(validate_sheet(df, contract, country))

    return failing


def validate_flat_source(df: pd.DataFrame, contract: SourceContract) -> list:
    actual_columns = list(df.columns)
    if actual_columns != contract.expected_columns:
        return [
            FailingCheck(
                "merged_header_misaligned",
                contract.source_name,
                f"expected {contract.expected_columns}, got {actual_columns}",
            )
        ]

    failing = []
    failing.extend(_field_checks(df, contract))
    failing.extend(_unit_checks(df, contract))
    failing.extend(_duplicate_key_checks(df, contract))
    return failing
