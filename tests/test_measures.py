"""Hand-built, isolated checks for each of the 9 measure definitions,
independent of datagen.py, plus the disagreement comparison over both a
hand-built duplicate-key case and the real deliberate-fixture scenarios.
"""
import pandas as pd
import pytest

from reconcilegate import measures
from reconcilegate.config import SEED
from reconcilegate.datagen import generate_clean_batch
from reconcilegate.measures_fixtures import build_duplicate_scenarios


def _shipment_sheet(rows):
    return {"IT": pd.DataFrame(rows)}


def test_shipped_kg_total_converts_non_canonical_units():
    sheets = _shipment_sheet([
        {"Order ID": "A", "Quantity": 10.0, "Unit": "kg"},
        {"Order ID": "B", "Quantity": 2.0, "Unit": "lb"},
    ])
    result = measures.shipped_kg_total(sheets)
    assert result["IT"] == pytest.approx(10.0 + 2.0 * 0.453592)


def test_shipment_event_count_rows_counts_every_row_including_duplicates():
    sheets = _shipment_sheet([
        {"Order ID": "A", "Quantity": 1.0, "Unit": "kg"},
        {"Order ID": "A", "Quantity": 1.0, "Unit": "kg"},
    ])
    assert measures.shipment_event_count_rows(sheets)["IT"] == 2


def test_shipment_event_count_distinct_key_collapses_duplicates():
    sheets = _shipment_sheet([
        {"Order ID": "A", "Quantity": 1.0, "Unit": "kg"},
        {"Order ID": "A", "Quantity": 1.0, "Unit": "kg"},
    ])
    assert measures.shipment_event_count_distinct_key(sheets)["IT"] == 1


def test_returns_volume_l_total_converts_ml():
    sheets = {"IT": pd.DataFrame([
        {"Volume": 1.0, "Unit": "L"},
        {"Volume": 500.0, "Unit": "mL"},
    ])}
    assert measures.returns_volume_l_total(sheets)["IT"] == pytest.approx(1.5)


def test_return_event_count_rows():
    sheets = {"IT": pd.DataFrame([{"Volume": 1.0, "Unit": "L"}] * 3)}
    assert measures.return_event_count_rows(sheets)["IT"] == 3


def test_return_rate_pct_uses_distinct_key_denominator():
    returns_sheets = {"IT": pd.DataFrame([{"Volume": 1.0, "Unit": "L"}] * 2)}
    shipment_sheets = _shipment_sheet([
        {"Order ID": "A", "Quantity": 1.0, "Unit": "kg"},
        {"Order ID": "A", "Quantity": 1.0, "Unit": "kg"},  # duplicate: distinct count is 1, not 2
    ])
    # 2 returns / 1 distinct shipment = 200%, not 2 returns / 2 rows = 100%
    assert measures.return_rate_pct(returns_sheets, shipment_sheets)["IT"] == pytest.approx(200.0)


def test_downtime_hours_total_converts_minutes():
    sheets = {"IT": pd.DataFrame([
        {"Duration": 1.0, "Unit": "hours"},
        {"Duration": 30.0, "Unit": "minutes"},
    ])}
    assert measures.downtime_hours_total(sheets)["IT"] == pytest.approx(1.5)


def test_downtime_event_count_rows():
    sheets = {"IT": pd.DataFrame([{"Duration": 1.0, "Unit": "hours"}] * 4)}
    assert measures.downtime_event_count_rows(sheets)["IT"] == 4


def test_complaint_event_count_rows():
    sheets = {"IT": pd.DataFrame([{"Category": "Labeling"}] * 5)}
    assert measures.complaint_event_count_rows(sheets)["IT"] == 5


def test_render_reports_exposes_nine_measure_definitions():
    batch = generate_clean_batch(SEED, month=10)
    rendered = measures.render_reports(batch)
    assert set(rendered.keys()) == {
        "shipment_performance", "returns_and_quality", "downtime_and_reliability", "complaint_summary",
    }
    n_measures = sum(len(v) for v in rendered.values())
    assert n_measures == 9


def test_disagreement_fires_on_a_hand_built_duplicate_key():
    batch = {"shipment_log": _shipment_sheet([
        {"Order ID": "A", "Quantity": 1.0, "Unit": "kg"},
        {"Order ID": "A", "Quantity": 1.0, "Unit": "kg"},
    ])}
    found = measures.find_shipments_this_period_disagreements(batch)
    assert len(found) == 1
    assert found[0]["plant"] == "IT"
    assert found[0]["shipment_performance_report_value"] == 2
    assert found[0]["returns_and_quality_report_value"] == 1
    assert "distinct Order IDs" in found[0]["definition_difference"]


def test_disagreement_does_not_fire_on_clean_data():
    batch = generate_clean_batch(SEED, month=11)
    assert measures.find_shipments_this_period_disagreements(batch) == []


def test_disagreement_does_not_fire_across_twenty_independent_clean_loads():
    false_positives = 0
    for month in range(20):
        batch = generate_clean_batch(SEED, month=month)
        false_positives += len(measures.find_shipments_this_period_disagreements(batch))
    assert false_positives == 0


def test_three_deliberate_scenarios_each_produce_exactly_one_disagreement():
    scenarios = build_duplicate_scenarios()
    assert len(scenarios) == 3
    total = 0
    for month, batch in scenarios:
        found = measures.find_shipments_this_period_disagreements(batch)
        assert len(found) == 1, f"month {month} expected exactly one disagreement, got {found}"
        total += len(found)
    assert total == 3
