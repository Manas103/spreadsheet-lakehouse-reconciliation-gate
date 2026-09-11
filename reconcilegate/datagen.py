"""Generates one "load" (one month's worth of all 6 sources) either clean
or with exactly one seeded defect injected, deterministic from
(base_seed, month, defect_type). A load is the unit the gate evaluates:
6 sources in, one publish/quarantine decision out.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from reconcilegate.config import COUNTRIES, UNIT_CONVERSION

N_ROWS_PER_COUNTRY = 15

TRUE_SHIPPED_KG_RANGE = (8000.0, 15000.0)
TRUE_RETURN_L_RANGE = (300.0, 900.0)

DOWNTIME_UNITS = ["hours", "minutes"]
COMPLAINT_CATEGORIES = ["Packaging", "Labeling", "Viscosity", "Particulates", "Delivery Damage"]
COMPLAINT_SEVERITIES = ["Low", "Medium", "High"]


def _rng(base_seed: int, month: int, salt: str = "") -> np.random.Generator:
    return np.random.default_rng(abs(hash((base_seed, month, salt))) % (2**32))


def _split_total(rng: np.random.Generator, total: float, n: int) -> np.ndarray:
    weights = rng.dirichlet(np.ones(n) * 3.0)
    return total * weights


def _make_unit_mixed_rows(rng: np.random.Generator, amounts_canonical: np.ndarray, unit_source: str):
    """Returns (values_in_shown_unit, unit_labels) such that converting
    value * factor[unit] back to canonical reproduces amounts_canonical
    exactly (clean-load construction, not a tuned measurement)."""
    factors = UNIT_CONVERSION[unit_source]["factors"]
    canonical = UNIT_CONVERSION[unit_source]["canonical"]
    non_canonical = [u for u in factors if u != canonical]
    unit_choice = rng.choice([canonical] + non_canonical, size=len(amounts_canonical))
    values = np.array(
        [amt / factors[u] for amt, u in zip(amounts_canonical, unit_choice)]
    )
    return values, unit_choice


def generate_clean_batch(base_seed: int, month: int) -> dict:
    rng_global = _rng(base_seed, month, "global")

    true_shipped_kg = {c: rng_global.uniform(*TRUE_SHIPPED_KG_RANGE) for c in COUNTRIES}
    true_return_l = {c: rng_global.uniform(*TRUE_RETURN_L_RANGE) for c in COUNTRIES}

    wms_extract = pd.DataFrame(
        [{"plant": c, "month": month, "shipped_kg_total": true_shipped_kg[c]} for c in COUNTRIES]
    )
    erp_extract = pd.DataFrame(
        [{"plant": c, "month": month, "return_volume_l_total": true_return_l[c]} for c in COUNTRIES]
    )

    shipment_sheets = {}
    returns_sheets = {}
    downtime_sheets = {}
    complaint_sheets = {}

    for c in COUNTRIES:
        rng = _rng(base_seed, month, f"ship-{c}")
        amounts = _split_total(rng, true_shipped_kg[c], N_ROWS_PER_COUNTRY)
        values, units = _make_unit_mixed_rows(rng, amounts, "shipment_log")
        shipment_sheets[c] = pd.DataFrame(
            {
                "Order ID": [f"SHP-{month:02d}-{c}-{i:03d}" for i in range(N_ROWS_PER_COUNTRY)],
                "Plant": c,
                "Month": month,
                "Quantity": np.round(values, 3),
                "Unit": units,
            }
        )

        rng = _rng(base_seed, month, f"ret-{c}")
        amounts = _split_total(rng, true_return_l[c], N_ROWS_PER_COUNTRY)
        values, units = _make_unit_mixed_rows(rng, amounts, "returns_register")
        returns_sheets[c] = pd.DataFrame(
            {
                "Return ID": [f"RET-{month:02d}-{c}-{i:03d}" for i in range(N_ROWS_PER_COUNTRY)],
                "Plant": c,
                "Month": month,
                "Volume": np.round(values, 3),
                "Unit": units,
            }
        )

        rng = _rng(base_seed, month, f"down-{c}")
        hours = rng.uniform(0.5, 24.0, size=N_ROWS_PER_COUNTRY)
        unit_choice = rng.choice(DOWNTIME_UNITS, size=N_ROWS_PER_COUNTRY)
        factors = UNIT_CONVERSION["downtime_log"]["factors"]
        values = np.array([h / factors[u] for h, u in zip(hours, unit_choice)])
        downtime_sheets[c] = pd.DataFrame(
            {
                "Event ID": [f"DWN-{month:02d}-{c}-{i:03d}" for i in range(N_ROWS_PER_COUNTRY)],
                "Plant": c,
                "Month": month,
                "Duration": np.round(values, 3),
                "Unit": unit_choice,
            }
        )

        rng = _rng(base_seed, month, f"cmp-{c}")
        complaint_sheets[c] = pd.DataFrame(
            {
                "Complaint ID": [f"CMP-{month:02d}-{c}-{i:03d}" for i in range(N_ROWS_PER_COUNTRY)],
                "Plant": c,
                "Month": month,
                "Category": rng.choice(COMPLAINT_CATEGORIES, size=N_ROWS_PER_COUNTRY),
                "Severity": rng.choice(COMPLAINT_SEVERITIES, size=N_ROWS_PER_COUNTRY),
            }
        )

    return {
        "shipment_log": shipment_sheets,
        "returns_register": returns_sheets,
        "downtime_log": downtime_sheets,
        "complaint_tracker": complaint_sheets,
        "erp_order_extract": erp_extract,
        "wms_shipment_extract": wms_extract,
    }


# --- defect injection -------------------------------------------------

EXCEL_SOURCES_WITH_UNIT = ["shipment_log", "returns_register", "downtime_log"]
ALL_EXCEL_SOURCES = ["shipment_log", "returns_register", "downtime_log", "complaint_tracker"]


def inject_missing_required_tab(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    source = rng.choice(ALL_EXCEL_SOURCES)
    country = rng.choice(COUNTRIES)
    batch = dict(batch)
    batch[source] = {c: df for c, df in batch[source].items() if c != country}
    return batch, source, f"missing_required_tab:{source}:{country}"


def inject_merged_header_misaligned(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    source = rng.choice(ALL_EXCEL_SOURCES)
    country = rng.choice(COUNTRIES)
    batch = dict(batch)
    batch = {**batch, "_header_overrides": {**batch.get("_header_overrides", {}), source: {country: True}}}
    return batch, source, f"merged_header_misaligned:{source}:{country}"


def inject_unexpected_unit_value(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    source = rng.choice(EXCEL_SOURCES_WITH_UNIT)
    country = rng.choice(COUNTRIES)
    batch = {**batch, source: {**batch[source]}}
    df = batch[source][country].copy()
    idx = rng.integers(0, len(df))
    unit_col = df.columns[-1]
    df.loc[idx, unit_col] = "grams"  # not in any contract's unit whitelist
    batch[source][country] = df
    return batch, source, f"unexpected_unit_value:{source}:{country}"


def inject_type_mismatch(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    source = rng.choice(EXCEL_SOURCES_WITH_UNIT)
    country = rng.choice(COUNTRIES)
    batch = {**batch, source: {**batch[source]}}
    df = batch[source][country].copy()
    idx = rng.integers(0, len(df))
    numeric_col = df.columns[-2]
    df[numeric_col] = df[numeric_col].astype(object)
    df.loc[idx, numeric_col] = "N/A"
    batch[source][country] = df
    return batch, source, f"type_mismatch:{source}:{country}"


def inject_null_in_required_field(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    source = rng.choice(ALL_EXCEL_SOURCES)
    country = rng.choice(COUNTRIES)
    batch = {**batch, source: {**batch[source]}}
    df = batch[source][country].copy()
    idx = rng.integers(0, len(df))
    df.loc[idx, "Plant"] = None
    batch[source][country] = df
    return batch, source, f"null_in_required_field:{source}:{country}"


def inject_out_of_range_value(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    source = rng.choice(EXCEL_SOURCES_WITH_UNIT)
    country = rng.choice(COUNTRIES)
    batch = {**batch, source: {**batch[source]}}
    df = batch[source][country].copy()
    idx = rng.integers(0, len(df))
    numeric_col = df.columns[-2]
    df.loc[idx, numeric_col] = -999.0
    batch[source][country] = df
    return batch, source, f"out_of_range_value:{source}:{country}"


def inject_duplicate_natural_key(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    source = rng.choice(ALL_EXCEL_SOURCES)
    country = rng.choice(COUNTRIES)
    batch = {**batch, source: {**batch[source]}}
    df = batch[source][country].copy()
    dup_row = df.iloc[[0]].copy()
    id_col = df.columns[0]
    dup_row[id_col] = df.iloc[1][id_col]  # collide with an existing key
    df = pd.concat([df, dup_row], ignore_index=True)
    batch[source][country] = df
    return batch, source, f"duplicate_natural_key:{source}:{country}"


def inject_reconciliation_mismatch(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    source = rng.choice(["shipment_log", "returns_register"])
    country = rng.choice(COUNTRIES)
    batch = dict(batch)
    if source == "shipment_log":
        sor_source, sor_col = "wms_shipment_extract", "shipped_kg_total"
    else:
        sor_source, sor_col = "erp_order_extract", "return_volume_l_total"
    sor_df = batch[sor_source].copy()
    mask = sor_df["plant"] == country
    sor_df.loc[mask, sor_col] = sor_df.loc[mask, sor_col] * 1.25  # 25% off, well past the 1% tolerance
    batch[sor_source] = sor_df
    return batch, source, f"reconciliation_mismatch:{source}:{country}"


DEFECT_INJECTORS = {
    "missing_required_tab": inject_missing_required_tab,
    "merged_header_misaligned": inject_merged_header_misaligned,
    "unexpected_unit_value": inject_unexpected_unit_value,
    "type_mismatch": inject_type_mismatch,
    "null_in_required_field": inject_null_in_required_field,
    "out_of_range_value": inject_out_of_range_value,
    "duplicate_natural_key": inject_duplicate_natural_key,
    "reconciliation_mismatch": inject_reconciliation_mismatch,
}


def generate_defect_batch(base_seed: int, month: int, defect_type: str) -> tuple[dict, str, str]:
    clean = generate_clean_batch(base_seed, month)
    rng = _rng(base_seed, month, f"defect-{defect_type}")
    injector = DEFECT_INJECTORS[defect_type]
    return injector(clean, rng)
