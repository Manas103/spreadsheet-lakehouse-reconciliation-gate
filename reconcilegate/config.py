"""Every simulation and contract constant lives here.

9 simulated vendor/operational sources (widened from the original 6):
  1. shipment_log            Excel workbook, per-country tabs, mixed weight units
  2. returns_register         Excel workbook, per-country tabs, mixed volume units
  3. downtime_log              Excel workbook, per-country tabs, mixed duration units
  4. complaint_tracker          Excel workbook, per-country tabs, no unit column
  5. erp_order_extract           CSV, system-of-record for order/return totals
  6. wms_shipment_extract         CSV, system-of-record for shipped-weight totals
  7. vendor_rate_catalog           cursor-paginated REST API, vendor labor rates
  8. vendor_claims_extract          fixed-width SFTP drop, vendor claims
  9. vendor_directory_feed            drifting-header CSV, vendor directory

Country/plant codes reuse the pharma-supply-kpi-lakehouse sibling's three
plants for thematic consistency; this repo is otherwise self-contained
and does not import from that repo. The 3 new vendor sources are not
plant/country scoped (a vendor rate catalog, a claims extract and a
vendor directory are enterprise-wide, not per-plant); they are keyed by
``cycle`` instead, the same integer load index the original 6 sources
call ``Month``/``month``.
"""

COUNTRIES = ["IT", "NL", "SG"]
SEED = 20260701

EXCEL_SOURCES = ["shipment_log", "returns_register", "downtime_log", "complaint_tracker"]
SOR_SOURCES = ["erp_order_extract", "wms_shipment_extract"]
VENDOR_SOURCES = ["vendor_rate_catalog", "vendor_claims_extract", "vendor_directory_feed"]
ALL_SOURCES = EXCEL_SOURCES + SOR_SOURCES + VENDOR_SOURCES

# unit -> canonical-unit conversion factor, per source that has a unit column.
UNIT_CONVERSION = {
    "shipment_log": {"canonical": "kg", "factors": {"kg": 1.0, "lb": 0.453592}},
    "returns_register": {"canonical": "L", "factors": {"L": 1.0, "mL": 0.001}},
    "downtime_log": {"canonical": "hours", "factors": {"hours": 1.0, "minutes": 1.0 / 60.0}},
}

RECONCILIATION_TOLERANCE_PCT = 1.0  # a load is quarantined if abs(pct diff) exceeds this

# reconciliation: excel source -> (system-of-record source, sor total column).
# The excel-side value/unit columns are read off that source's own contract
# (contracts.py), not duplicated here. Only the original two excel sources
# have a system-of-record counterpart; the 3 new vendor sources are
# contract-checked and watermarked but have no reconciliation target in
# this design (disclosed in the README, same honesty pattern as
# downtime_log / complaint_tracker before them).
RECONCILIATION_TARGETS = {
    "shipment_log": {"sor_source": "wms_shipment_extract", "sor_value_col": "shipped_kg_total"},
    "returns_register": {"sor_source": "erp_order_extract", "sor_value_col": "return_volume_l_total"},
}

N_CLEAN_LOADS = 20
N_SEEDED_DEFECTS = 40

# 8 original defect categories, counts summing to 30, unchanged from the
# 6-source benchmark: same sources, same injectors, same RNG draws.
DEFECT_COUNTS_ORIGINAL = {
    "missing_required_tab": 3,
    "merged_header_misaligned": 3,
    "unexpected_unit_value": 4,
    "type_mismatch": 4,
    "null_in_required_field": 4,
    "out_of_range_value": 4,
    "duplicate_natural_key": 4,
    "reconciliation_mismatch": 4,
}
assert sum(DEFECT_COUNTS_ORIGINAL.values()) == 30

# 10 extra defect instances targeting the 3 new vendor sources: the 2
# defect types native to the new formats (fixed_width_field_misaligned,
# csv_header_drift) get 3 instances each (one per corruption flavor,
# see datagen.py), and the 3 new sources each pick up one more instance
# of an existing defect type that applies to their own shape.
DEFECT_COUNTS_VENDOR = {
    "fixed_width_field_misaligned": 3,
    "csv_header_drift": 3,
    "type_mismatch": 1,  # vendor_rate_catalog
    "null_in_required_field": 1,  # vendor_rate_catalog
    "out_of_range_value": 1,  # vendor_rate_catalog
    "duplicate_natural_key": 1,  # vendor_claims_extract
}
assert sum(DEFECT_COUNTS_VENDOR.values()) == 10

# Merged view: 10 defect types, counts summing to 40. This is the dict
# the benchmark script and README report against.
DEFECT_COUNTS = dict(DEFECT_COUNTS_ORIGINAL)
for k, v in DEFECT_COUNTS_VENDOR.items():
    DEFECT_COUNTS[k] = DEFECT_COUNTS.get(k, 0) + v
assert sum(DEFECT_COUNTS.values()) == N_SEEDED_DEFECTS

MAX_ATTEMPTS = 3

# --- vendor source generation constants --------------------------------

VENDOR_LABOR_CATEGORIES = ["Body", "Mechanical", "Glass", "Paint", "Diagnostics"]
VENDOR_CODES = [f"V{i:05d}" for i in range(1, 9)]
VENDOR_RATE_ROWS_PER_CYCLE = 12
VENDOR_RATE_USD_RANGE = (35.0, 185.0)

VENDOR_CLAIMS_ROWS_PER_CYCLE = 10
VENDOR_CLAIM_STATUS_CODES = ["AP", "PD", "RJ"]
VENDOR_CLAIM_AMOUNT_CENTS_RANGE = (5000, 850000)

VENDOR_DIRECTORY_ROWS_PER_CYCLE = 8
VENDOR_DIRECTORY_STATUS = ["ACTIVE", "SUSPENDED", "PENDING"]
VENDOR_DIRECTORY_REGIONS = ["NE", "SE", "MW", "W"]
