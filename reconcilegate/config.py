"""Every simulation and contract constant lives here.

6 simulated operational sources, matching the JD's count:
  1. shipment_log        Excel workbook, per-country tabs, mixed weight units
  2. returns_register     Excel workbook, per-country tabs, mixed volume units
  3. downtime_log          Excel workbook, per-country tabs, mixed duration units
  4. complaint_tracker      Excel workbook, per-country tabs, no unit column
  5. erp_order_extract       CSV, system-of-record for order/return totals
  6. wms_shipment_extract     CSV, system-of-record for shipped-weight totals

Country/plant codes reuse the pharma-supply-kpi-lakehouse sibling's three
plants for thematic consistency; this repo is otherwise self-contained
and does not import from that repo.
"""

COUNTRIES = ["IT", "NL", "SG"]
SEED = 20260701

EXCEL_SOURCES = ["shipment_log", "returns_register", "downtime_log", "complaint_tracker"]
SOR_SOURCES = ["erp_order_extract", "wms_shipment_extract"]
ALL_SOURCES = EXCEL_SOURCES + SOR_SOURCES

# unit -> canonical-unit conversion factor, per source that has a unit column.
UNIT_CONVERSION = {
    "shipment_log": {"canonical": "kg", "factors": {"kg": 1.0, "lb": 0.453592}},
    "returns_register": {"canonical": "L", "factors": {"L": 1.0, "mL": 0.001}},
    "downtime_log": {"canonical": "hours", "factors": {"hours": 1.0, "minutes": 1.0 / 60.0}},
}

RECONCILIATION_TOLERANCE_PCT = 1.0  # a load is quarantined if abs(pct diff) exceeds this

# reconciliation: excel source -> (system-of-record source, sor total column).
# The excel-side value/unit columns are read off that source's own contract
# (contracts.py), not duplicated here.
RECONCILIATION_TARGETS = {
    "shipment_log": {"sor_source": "wms_shipment_extract", "sor_value_col": "shipped_kg_total"},
    "returns_register": {"sor_source": "erp_order_extract", "sor_value_col": "return_volume_l_total"},
}

N_CLEAN_LOADS = 20
N_SEEDED_DEFECTS = 30

# 8 defect categories, counts summing to N_SEEDED_DEFECTS.
DEFECT_COUNTS = {
    "missing_required_tab": 3,
    "merged_header_misaligned": 3,
    "unexpected_unit_value": 4,
    "type_mismatch": 4,
    "null_in_required_field": 4,
    "out_of_range_value": 4,
    "duplicate_natural_key": 4,
    "reconciliation_mismatch": 4,
}
assert sum(DEFECT_COUNTS.values()) == N_SEEDED_DEFECTS

MAX_ATTEMPTS = 3
