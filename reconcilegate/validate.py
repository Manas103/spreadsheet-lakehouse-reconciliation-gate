"""Runs a source's declarative contract (contracts.py) against parsed
data (read back through excel_io.py / pandas), returning a list of named
failing checks. Nothing here is source-specific `if` logic; every rule
comes out of the contract object passed in.
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


def validate_sheet(df: pd.DataFrame, contract: SourceContract, country: str) -> list:
    """Assumes the tab exists (missing_required_tab is checked one level up)."""
    failing = []

    actual_columns = list(df.columns)
    if actual_columns != contract.expected_columns:
        failing.append(
            FailingCheck(
                "merged_header_misaligned",
                contract.source_name,
                f"{country}: expected {contract.expected_columns}, got {actual_columns}",
            )
        )
        return failing  # column meaning is unreliable past this point

    # The field immediately before unit_field is denominated in whatever
    # unit that row's unit column names, not necessarily the canonical
    # unit its min_value/max_value were written against; convert before
    # range-checking it, or a valid mL row (e.g. 60 L = 60,000 mL) reads
    # as wildly out of range against an L-scale limit. See README
    # Findings for the run that surfaced this.
    unit_converted_field = contract.fields[-2].name if contract.unit_field else None
    factors = UNIT_CONVERSION.get(contract.source_name, {}).get("factors", {})

    for field in contract.fields:
        col = df[field.name]
        for row_idx, value in col.items():
            if _is_missing(value):
                if not field.nullable:
                    failing.append(
                        FailingCheck(
                            "null_in_required_field",
                            contract.source_name,
                            f"{country} row {row_idx}: {field.name} is null",
                        )
                    )
                continue
            if field.dtype in ("int", "float"):
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    failing.append(
                        FailingCheck(
                            "type_mismatch",
                            contract.source_name,
                            f"{country} row {row_idx}: {field.name}={value!r} is not numeric",
                        )
                    )
                    continue
                range_check_value = numeric
                if field.name == unit_converted_field:
                    row_unit = df.loc[row_idx, contract.unit_field]
                    if row_unit in factors:
                        range_check_value = numeric * factors[row_unit]
                if field.min_value is not None and range_check_value < field.min_value:
                    failing.append(
                        FailingCheck(
                            "out_of_range_value",
                            contract.source_name,
                            f"{country} row {row_idx}: {field.name}={numeric} < {field.min_value}",
                        )
                    )
                if field.max_value is not None and range_check_value > field.max_value:
                    failing.append(
                        FailingCheck(
                            "out_of_range_value",
                            contract.source_name,
                            f"{country} row {row_idx}: {field.name}={numeric} > {field.max_value}",
                        )
                    )

    if contract.unit_field is not None:
        valid_units = set(UNIT_CONVERSION[contract.source_name]["factors"].keys())
        bad = df[~df[contract.unit_field].isin(valid_units)]
        for row_idx in bad.index:
            failing.append(
                FailingCheck(
                    "unexpected_unit_value",
                    contract.source_name,
                    f"{country} row {row_idx}: unit={df.loc[row_idx, contract.unit_field]!r} not in {sorted(valid_units)}",
                )
            )

    natural_key = contract.natural_key
    if natural_key and all(k in df.columns for k in natural_key):
        dup_mask = df.duplicated(subset=natural_key, keep=False)
        for row_idx in df[dup_mask].index:
            key_val = tuple(df.loc[row_idx, k] for k in natural_key)
            failing.append(
                FailingCheck(
                    "duplicate_natural_key",
                    contract.source_name,
                    f"{country} row {row_idx}: key {key_val} duplicated",
                )
            )

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
    failing = []
    actual_columns = list(df.columns)
    if actual_columns != contract.expected_columns:
        failing.append(
            FailingCheck(
                "merged_header_misaligned",
                contract.source_name,
                f"expected {contract.expected_columns}, got {actual_columns}",
            )
        )
        return failing

    for field in contract.fields:
        col = df[field.name]
        for row_idx, value in col.items():
            if _is_missing(value):
                if not field.nullable:
                    failing.append(
                        FailingCheck("null_in_required_field", contract.source_name, f"row {row_idx}: {field.name} is null")
                    )
                continue
            if field.dtype in ("int", "float"):
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    failing.append(
                        FailingCheck("type_mismatch", contract.source_name, f"row {row_idx}: {field.name}={value!r}")
                    )
                    continue
                if field.min_value is not None and numeric < field.min_value:
                    failing.append(
                        FailingCheck("out_of_range_value", contract.source_name, f"row {row_idx}: {field.name}={numeric}")
                    )
    return failing
