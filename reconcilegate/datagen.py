"""Generates one "load" (one month's worth of all 6 sources) either clean
or with exactly one seeded defect injected, deterministic from
(base_seed, month, defect_type). A load is the unit the gate evaluates:
6 sources in, one publish/quarantine decision out.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from reconcilegate.config import (
    COUNTRIES,
    UNIT_CONVERSION,
    VENDOR_CLAIM_AMOUNT_CENTS_RANGE,
    VENDOR_CLAIM_STATUS_CODES,
    VENDOR_CLAIMS_ROWS_PER_CYCLE,
    VENDOR_CODES,
    VENDOR_DIRECTORY_REGIONS,
    VENDOR_DIRECTORY_ROWS_PER_CYCLE,
    VENDOR_DIRECTORY_STATUS,
    VENDOR_LABOR_CATEGORIES,
    VENDOR_RATE_ROWS_PER_CYCLE,
    VENDOR_RATE_USD_RANGE,
)
from reconcilegate.drifting_csv import BROKEN_VARIANT_HEADERS, VARIANT_HEADERS

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

    rng = _rng(base_seed, month, "vendor-rate")
    vendor_rate_catalog = [
        {
            "rate_id": f"RATE-{month:03d}-{i:03d}",
            "vendor_code": str(rng.choice(VENDOR_CODES)),
            "labor_category": str(rng.choice(VENDOR_LABOR_CATEGORIES)),
            "hourly_rate_usd": round(float(rng.uniform(*VENDOR_RATE_USD_RANGE)), 2),
            "cycle": month,
            "updated_at": f"2026-{(month % 12) + 1:02d}-01T00:00:00",
        }
        for i in range(VENDOR_RATE_ROWS_PER_CYCLE)
    ]

    rng = _rng(base_seed, month, "vendor-claims")
    vendor_claims_extract = [
        {
            "claim_ref": f"CLM-{month * 1000 + i:06d}",
            "vendor_code": str(rng.choice(VENDOR_CODES)),
            "plant": str(rng.choice(COUNTRIES)),
            "amount_cents": int(rng.integers(*VENDOR_CLAIM_AMOUNT_CENTS_RANGE)),
            "status_code": str(rng.choice(VENDOR_CLAIM_STATUS_CODES)),
            "cycle": month,
        }
        for i in range(VENDOR_CLAIMS_ROWS_PER_CYCLE)
    ]

    rng = _rng(base_seed, month, "vendor-directory")
    vendor_directory_rows = [
        {
            "vendor_id": f"VND-{i:04d}",
            "vendor_name": f"Vendor {i:04d} LLC",
            "tax_id": f"TAX{month:03d}{i:03d}",
            "status": str(rng.choice(VENDOR_DIRECTORY_STATUS)),
            "cycle": month,
            "region": str(rng.choice(VENDOR_DIRECTORY_REGIONS)),
        }
        for i in range(VENDOR_DIRECTORY_ROWS_PER_CYCLE)
    ]
    variant_name = list(VARIANT_HEADERS.keys())[month % len(VARIANT_HEADERS)]

    return {
        "shipment_log": shipment_sheets,
        "returns_register": returns_sheets,
        "downtime_log": downtime_sheets,
        "complaint_tracker": complaint_sheets,
        "erp_order_extract": erp_extract,
        "wms_shipment_extract": wms_extract,
        "vendor_rate_catalog": vendor_rate_catalog,
        "vendor_claims_extract": vendor_claims_extract,
        "vendor_directory_feed": {"rows": vendor_directory_rows, "header": VARIANT_HEADERS[variant_name]},
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


def generate_defect_batch(base_seed: int, month: int, defect_type: str, pool: str = "original") -> tuple[dict, str, str]:
    """``pool="original"`` reproduces the exact 8-type/6-source RNG stream
    and injectors this repo shipped with at 30/30. ``pool="vendor"`` is
    the 10-extra-instance pool added to reach 40/40: the 2 defect types
    native to the 3 new source formats, plus one more instance of an
    existing type targeted specifically at a vendor source (see
    config.DEFECT_COUNTS_VENDOR)."""
    clean = generate_clean_batch(base_seed, month)
    injectors = DEFECT_INJECTORS if pool == "original" else VENDOR_DEFECT_INJECTORS
    salt = f"defect-{defect_type}" if pool == "original" else f"defect-vendor-{defect_type}"
    rng = _rng(base_seed, month, salt)
    injector = injectors[defect_type]
    return injector(clean, rng)


# --- vendor-source defect injection (10 extra instances, 2 new types) -

VENDOR_RATE_SOURCE = "vendor_rate_catalog"
VENDOR_CLAIMS_SOURCE = "vendor_claims_extract"
VENDOR_DIRECTORY_SOURCE = "vendor_directory_feed"
FIXED_WIDTH_CORRUPT_FLAVORS = ["short", "shifted"]


def inject_type_mismatch_vendor_rate(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    batch = dict(batch)
    rows = [dict(r) for r in batch[VENDOR_RATE_SOURCE]]
    idx = int(rng.integers(0, len(rows)))
    rows[idx]["hourly_rate_usd"] = "N/A"
    batch[VENDOR_RATE_SOURCE] = rows
    return batch, VENDOR_RATE_SOURCE, f"type_mismatch:{VENDOR_RATE_SOURCE}:row{idx}"


def inject_null_in_required_field_vendor_rate(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    batch = dict(batch)
    rows = [dict(r) for r in batch[VENDOR_RATE_SOURCE]]
    idx = int(rng.integers(0, len(rows)))
    rows[idx]["vendor_code"] = None
    batch[VENDOR_RATE_SOURCE] = rows
    return batch, VENDOR_RATE_SOURCE, f"null_in_required_field:{VENDOR_RATE_SOURCE}:row{idx}"


def inject_out_of_range_value_vendor_rate(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    batch = dict(batch)
    rows = [dict(r) for r in batch[VENDOR_RATE_SOURCE]]
    idx = int(rng.integers(0, len(rows)))
    rows[idx]["hourly_rate_usd"] = -50.0
    batch[VENDOR_RATE_SOURCE] = rows
    return batch, VENDOR_RATE_SOURCE, f"out_of_range_value:{VENDOR_RATE_SOURCE}:row{idx}"


def inject_duplicate_natural_key_vendor_claims(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    batch = dict(batch)
    rows = [dict(r) for r in batch[VENDOR_CLAIMS_SOURCE]]
    dup = dict(rows[0])
    dup["claim_ref"] = rows[1]["claim_ref"]
    rows.append(dup)
    batch[VENDOR_CLAIMS_SOURCE] = rows
    return batch, VENDOR_CLAIMS_SOURCE, f"duplicate_natural_key:{VENDOR_CLAIMS_SOURCE}"


def inject_fixed_width_field_misaligned(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    rows = batch[VENDOR_CLAIMS_SOURCE]
    idx = int(rng.integers(0, len(rows)))
    flavor = str(rng.choice(FIXED_WIDTH_CORRUPT_FLAVORS))
    batch = {**batch, "_fixed_width_corrupt": {idx: flavor}}
    return batch, VENDOR_CLAIMS_SOURCE, f"fixed_width_field_misaligned:{VENDOR_CLAIMS_SOURCE}:row{idx}:{flavor}"


def inject_csv_header_drift(batch: dict, rng: np.random.Generator) -> tuple[dict, str, str]:
    variant = str(rng.choice(list(BROKEN_VARIANT_HEADERS.keys())))
    batch = dict(batch)
    directory = dict(batch[VENDOR_DIRECTORY_SOURCE])
    directory["header"] = BROKEN_VARIANT_HEADERS[variant]
    batch[VENDOR_DIRECTORY_SOURCE] = directory
    return batch, VENDOR_DIRECTORY_SOURCE, f"csv_header_drift:{VENDOR_DIRECTORY_SOURCE}:{variant}"


VENDOR_DEFECT_INJECTORS = {
    "fixed_width_field_misaligned": inject_fixed_width_field_misaligned,
    "csv_header_drift": inject_csv_header_drift,
    "type_mismatch": inject_type_mismatch_vendor_rate,
    "null_in_required_field": inject_null_in_required_field_vendor_rate,
    "out_of_range_value": inject_out_of_range_value_vendor_rate,
    "duplicate_natural_key": inject_duplicate_natural_key_vendor_claims,
}
