import pandas as pd

from reconcilegate.excel_io import SheetLayout, read_workbook, write_workbook

LAYOUT = SheetLayout(id_columns=["Order ID", "Plant", "Month"], group_label="Shipment", group_fields=["Quantity", "Unit"])


def test_round_trip_reconstructs_merged_header_exactly(tmp_path):
    df = pd.DataFrame(
        {
            "Order ID": ["A-1", "A-2"],
            "Plant": ["IT", "IT"],
            "Month": [0, 0],
            "Quantity": [10.5, 20.25],
            "Unit": ["kg", "lb"],
        }
    )
    path = str(tmp_path / "wb.xlsx")
    write_workbook(path, {"IT": df}, LAYOUT)
    sheets = read_workbook(path)

    assert list(sheets.keys()) == ["IT"]
    got = sheets["IT"]
    assert list(got.columns) == ["Order ID", "Plant", "Month", "Shipment: Quantity", "Shipment: Unit"]
    assert list(got["Order ID"]) == ["A-1", "A-2"]
    assert list(got["Shipment: Quantity"]) == [10.5, 20.25]
    assert list(got["Shipment: Unit"]) == ["kg", "lb"]


def test_multiple_country_tabs_round_trip(tmp_path):
    df_it = pd.DataFrame({"Order ID": ["A"], "Plant": ["IT"], "Month": [1], "Quantity": [1.0], "Unit": ["kg"]})
    df_nl = pd.DataFrame({"Order ID": ["B"], "Plant": ["NL"], "Month": [1], "Quantity": [2.0], "Unit": ["kg"]})
    path = str(tmp_path / "wb2.xlsx")
    write_workbook(path, {"IT": df_it, "NL": df_nl}, LAYOUT)
    sheets = read_workbook(path)
    assert set(sheets.keys()) == {"IT", "NL"}


def test_header_label_override_produces_misaligned_header(tmp_path):
    df = pd.DataFrame({"Order ID": ["A"], "Plant": ["IT"], "Month": [0], "Quantity": [10.0], "Unit": ["kg"]})
    path = str(tmp_path / "wb3.xlsx")
    write_workbook(path, {"IT": df}, LAYOUT, header_label_override={"IT": ["Unit", "Quantity"]})
    sheets = read_workbook(path)
    got_columns = list(sheets["IT"].columns)
    # The reconstructed header no longer matches the layout's canonical order.
    assert got_columns != ["Order ID", "Plant", "Month", "Shipment: Quantity", "Shipment: Unit"]
    assert got_columns == ["Order ID", "Plant", "Month", "Shipment: Unit", "Shipment: Quantity"]
