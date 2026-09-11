"""Reconciles the two unit-mixed Excel sources against their system-of-
record totals, in canonical units, per plant. Only runs for a source once
its own contract checks (validate.py) have passed, since a reconciliation
number computed over a source with a header or type problem is meaningless.
"""
from __future__ import annotations

import pandas as pd

from reconcilegate.config import RECONCILIATION_TARGETS, RECONCILIATION_TOLERANCE_PCT, UNIT_CONVERSION
from reconcilegate.contracts import CONTRACTS
from reconcilegate.validate import FailingCheck


def _canonical_total_by_plant(sheets: dict, source_name: str, value_field: str, unit_field: str) -> pd.Series:
    factors = UNIT_CONVERSION[source_name]["factors"]
    totals = {}
    for country, df in sheets.items():
        canonical_values = df.apply(lambda row: float(row[value_field]) * factors[row[unit_field]], axis=1)
        totals[country] = canonical_values.sum()
    return pd.Series(totals)


def reconcile_source(source_name: str, sheets: dict, sor_df: pd.DataFrame) -> list:
    target = RECONCILIATION_TARGETS[source_name]
    contract = CONTRACTS[source_name]
    unit_field = contract.unit_field
    value_field = contract.fields[-2].name  # the numeric field immediately before the unit field

    excel_totals = _canonical_total_by_plant(sheets, source_name, value_field, unit_field)
    sor_totals = sor_df.set_index("plant")[target["sor_value_col"]]

    failing = []
    for plant in excel_totals.index:
        if plant not in sor_totals.index:
            continue
        excel_total = excel_totals[plant]
        sor_total = sor_totals[plant]
        if sor_total == 0:
            continue
        pct_diff = 100.0 * abs(excel_total - sor_total) / abs(sor_total)
        if pct_diff > RECONCILIATION_TOLERANCE_PCT:
            failing.append(
                FailingCheck(
                    "reconciliation_mismatch",
                    source_name,
                    f"{plant}: excel_total={excel_total:.3f} sor_total={sor_total:.3f} "
                    f"pct_diff={pct_diff:.3f}% (tolerance {RECONCILIATION_TOLERANCE_PCT}%)",
                )
            )
    return failing
