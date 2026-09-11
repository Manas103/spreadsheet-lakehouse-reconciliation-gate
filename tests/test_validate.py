import pandas as pd

from reconcilegate.contracts import SHIPMENT_LOG
from reconcilegate.validate import validate_sheet


def _clean_df():
    return pd.DataFrame(
        {
            "Order ID": ["A-1", "A-2"],
            "Plant": ["IT", "IT"],
            "Month": [0, 0],
            "Shipment: Quantity": [10.0, 5.0],
            "Shipment: Unit": ["kg", "lb"],
        }
    )


def test_clean_sheet_has_no_failing_checks():
    failing = validate_sheet(_clean_df(), SHIPMENT_LOG, "IT")
    assert failing == []


def test_bad_header_order_flags_merged_header_misaligned():
    df = _clean_df()[["Order ID", "Plant", "Month", "Shipment: Unit", "Shipment: Quantity"]]
    failing = validate_sheet(df, SHIPMENT_LOG, "IT")
    assert len(failing) == 1
    assert failing[0].check == "merged_header_misaligned"


def test_null_required_field_flagged():
    df = _clean_df()
    df.loc[0, "Plant"] = None
    failing = validate_sheet(df, SHIPMENT_LOG, "IT")
    assert any(c.check == "null_in_required_field" for c in failing)


def test_type_mismatch_flagged():
    df = _clean_df()
    df["Shipment: Quantity"] = df["Shipment: Quantity"].astype(object)
    df.loc[0, "Shipment: Quantity"] = "N/A"
    failing = validate_sheet(df, SHIPMENT_LOG, "IT")
    assert any(c.check == "type_mismatch" for c in failing)


def test_out_of_range_flagged():
    df = _clean_df()
    df.loc[0, "Shipment: Quantity"] = -5.0
    failing = validate_sheet(df, SHIPMENT_LOG, "IT")
    assert any(c.check == "out_of_range_value" for c in failing)


def test_unexpected_unit_flagged():
    df = _clean_df()
    df.loc[0, "Shipment: Unit"] = "grams"
    failing = validate_sheet(df, SHIPMENT_LOG, "IT")
    assert any(c.check == "unexpected_unit_value" for c in failing)


def test_duplicate_natural_key_flagged():
    df = _clean_df()
    df.loc[1, "Order ID"] = "A-1"
    failing = validate_sheet(df, SHIPMENT_LOG, "IT")
    assert sum(1 for c in failing if c.check == "duplicate_natural_key") == 2
