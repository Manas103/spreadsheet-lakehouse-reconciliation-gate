"""Excel header layouts, one per workbook source. Kept separate from
``contracts.py`` because a layout describes how the header is physically
merged on the sheet (what ``excel_io.py`` writes and parses), while a
contract describes what is logically required (what ``validate.py``
checks); the two happen to agree on column names and order for every
source in this repo, and that agreement is exactly what
``merged_header_alignment`` checks.
"""
from __future__ import annotations

from reconcilegate.excel_io import SheetLayout

SHIPMENT_LAYOUT = SheetLayout(
    id_columns=["Order ID", "Plant", "Month"], group_label="Shipment", group_fields=["Quantity", "Unit"]
)
RETURNS_LAYOUT = SheetLayout(
    id_columns=["Return ID", "Plant", "Month"], group_label="Return", group_fields=["Volume", "Unit"]
)
DOWNTIME_LAYOUT = SheetLayout(
    id_columns=["Event ID", "Plant", "Month"], group_label="Downtime", group_fields=["Duration", "Unit"]
)
COMPLAINT_LAYOUT = SheetLayout(
    id_columns=["Complaint ID", "Plant", "Month"],
    group_label="Complaint",
    group_fields=["Category", "Severity"],
)

LAYOUTS = {
    "shipment_log": SHIPMENT_LAYOUT,
    "returns_register": RETURNS_LAYOUT,
    "downtime_log": DOWNTIME_LAYOUT,
    "complaint_tracker": COMPLAINT_LAYOUT,
}
