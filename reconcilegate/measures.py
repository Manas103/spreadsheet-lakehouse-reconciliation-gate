"""Nine tested measure definitions the four legacy Excel reports (Shipment
Performance, Returns & Quality, Downtime & Reliability, Complaint Summary)
are rendered from, plus the one comparison this extension exists to make:
two of those reports both display a figure called "Shipments This Period"
off the same shipment_log sheets, computed by two different, independently
legitimate definitions, and the two disagree exactly where a shipment_log
sheet has a duplicated natural key.

Every measure reads directly from the same per-country sheets
reconcilegate.datagen builds and reconcilegate.validate/gate already check;
nothing here re-derives its own copy of a source.
"""
from __future__ import annotations

from reconcilegate.config import UNIT_CONVERSION


def _canonical_sum(sheets: dict, value_col: str, unit_col: str, unit_source: str) -> dict:
    factors = UNIT_CONVERSION[unit_source]["factors"]
    return {
        plant: float((df[value_col] * df[unit_col].map(factors)).sum())
        for plant, df in sheets.items()
    }


def _row_count(sheets: dict) -> dict:
    return {plant: int(len(df)) for plant, df in sheets.items()}


def _distinct_key_count(sheets: dict, key_col: str) -> dict:
    return {plant: int(df[key_col].nunique()) for plant, df in sheets.items()}


# --- Report 1: Shipment Performance -------------------------------------

def shipped_kg_total(shipment_sheets: dict) -> dict:
    """Measure 1. Canonical-kg sum of every shipment_log row, per plant."""
    return _canonical_sum(shipment_sheets, "Quantity", "Unit", "shipment_log")


def shipment_event_count_rows(shipment_sheets: dict) -> dict:
    """Measure 2. Report 1's definition of "Shipments This Period": one
    count per row in shipment_log, per plant."""
    return _row_count(shipment_sheets)


# --- Report 2: Returns & Quality ----------------------------------------

def returns_volume_l_total(returns_sheets: dict) -> dict:
    """Measure 3. Canonical-L sum of every returns_register row, per plant."""
    return _canonical_sum(returns_sheets, "Volume", "Unit", "returns_register")


def return_event_count_rows(returns_sheets: dict) -> dict:
    """Measure 4. One count per row in returns_register, per plant."""
    return _row_count(returns_sheets)


def shipment_event_count_distinct_key(shipment_sheets: dict) -> dict:
    """Measure 5. Report 2's definition of "Shipments This Period": one
    count per distinct Order ID in shipment_log, per plant. This is the
    formula Report 2 actually needs, since a duplicated Order ID should
    not inflate the denominator of a rate computed against returns; it is
    a genuinely different definition from measure 2's, not a second
    implementation of the same one."""
    return _distinct_key_count(shipment_sheets, "Order ID")


def return_rate_pct(returns_sheets: dict, shipment_sheets: dict) -> dict:
    """Measure 6. Returns per 100 shipments, using measure 5's distinct-key
    shipment count as the denominator."""
    returns = return_event_count_rows(returns_sheets)
    shipments = shipment_event_count_distinct_key(shipment_sheets)
    return {
        plant: (100.0 * returns[plant] / shipments[plant]) if shipments.get(plant) else 0.0
        for plant in returns
    }


# --- Report 3: Downtime & Reliability ------------------------------------

def downtime_hours_total(downtime_sheets: dict) -> dict:
    """Measure 7. Canonical-hours sum of every downtime_log row, per plant."""
    return _canonical_sum(downtime_sheets, "Duration", "Unit", "downtime_log")


def downtime_event_count_rows(downtime_sheets: dict) -> dict:
    """Measure 8. One count per row in downtime_log, per plant."""
    return _row_count(downtime_sheets)


# --- Report 4: Complaint Summary ------------------------------------------

def complaint_event_count_rows(complaint_sheets: dict) -> dict:
    """Measure 9. One count per row in complaint_tracker, per plant."""
    return _row_count(complaint_sheets)


def render_reports(batch: dict) -> dict:
    """Renders all four reports' measures from one load's parsed sheets,
    the same shape reconcilegate.datagen.generate_clean_batch returns."""
    shipment_sheets = batch["shipment_log"]
    returns_sheets = batch["returns_register"]
    downtime_sheets = batch["downtime_log"]
    complaint_sheets = batch["complaint_tracker"]

    return {
        "shipment_performance": {
            "shipped_kg_total": shipped_kg_total(shipment_sheets),
            "shipments_this_period": shipment_event_count_rows(shipment_sheets),
        },
        "returns_and_quality": {
            "returns_volume_l_total": returns_volume_l_total(returns_sheets),
            "returns_this_period": return_event_count_rows(returns_sheets),
            "shipments_this_period": shipment_event_count_distinct_key(shipment_sheets),
            "return_rate_pct": return_rate_pct(returns_sheets, shipment_sheets),
        },
        "downtime_and_reliability": {
            "downtime_hours_total": downtime_hours_total(downtime_sheets),
            "downtime_events_this_period": downtime_event_count_rows(downtime_sheets),
        },
        "complaint_summary": {
            "complaints_this_period": complaint_event_count_rows(complaint_sheets),
        },
    }


def find_shipments_this_period_disagreements(batch: dict) -> list[dict]:
    """Report 1 (Shipment Performance) and Report 2 (Returns & Quality)
    both compute a "Shipments This Period" figure from the same
    shipment_log sheets, using two different, independently legitimate
    definitions (measure 2: row count; measure 5: distinct Order ID
    count). They agree whenever every row's Order ID is unique, and
    disagree exactly where it is not."""
    shipment_sheets = batch["shipment_log"]
    by_rows = shipment_event_count_rows(shipment_sheets)
    by_distinct_key = shipment_event_count_distinct_key(shipment_sheets)
    disagreements = []
    for plant in by_rows:
        rows_value = by_rows[plant]
        distinct_value = by_distinct_key.get(plant, rows_value)
        if rows_value != distinct_value:
            disagreements.append({
                "plant": plant,
                "shipment_performance_report_value": rows_value,
                "returns_and_quality_report_value": distinct_value,
                "definition_difference": (
                    "Shipment Performance counts shipment_log rows; Returns & Quality "
                    "counts distinct Order IDs; "
                    f"{rows_value - distinct_value} duplicated Order ID(s) in this plant's sheet."
                ),
            })
    return disagreements
