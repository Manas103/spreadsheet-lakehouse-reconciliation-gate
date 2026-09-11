"""Declarative per-source contracts. Every rule ``validate.py`` enforces is
data here, not a hardcoded `if` per source: column order and names, dtype,
nullability, numeric range, unit whitelist and canonical unit, and (for the
two sources with a system-of-record) the reconciliation target.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from reconcilegate.config import COUNTRIES, UNIT_CONVERSION


@dataclass(frozen=True)
class FieldSpec:
    name: str
    dtype: str  # "str", "int", "float", "bool_yn"
    nullable: bool = False
    min_value: float | None = None
    max_value: float | None = None


@dataclass(frozen=True)
class SourceContract:
    source_name: str
    is_excel: bool
    expected_columns: list  # canonical order, the merged-header alignment check
    fields: list  # list[FieldSpec]
    natural_key: list  # columns that together must be unique
    expected_countries: list = field(default_factory=lambda: list(COUNTRIES))
    unit_field: str | None = None


SHIPMENT_LOG = SourceContract(
    source_name="shipment_log",
    is_excel=True,
    expected_columns=["Order ID", "Plant", "Month", "Shipment: Quantity", "Shipment: Unit"],
    fields=[
        FieldSpec("Order ID", "str", nullable=False),
        FieldSpec("Plant", "str", nullable=False),
        FieldSpec("Month", "int", nullable=False, min_value=0, max_value=239),
        FieldSpec("Shipment: Quantity", "float", nullable=False, min_value=0, max_value=100000),
        FieldSpec("Shipment: Unit", "str", nullable=False),
    ],
    natural_key=["Order ID"],
    unit_field="Shipment: Unit",
)

RETURNS_REGISTER = SourceContract(
    source_name="returns_register",
    is_excel=True,
    expected_columns=["Return ID", "Plant", "Month", "Return: Volume", "Return: Unit"],
    fields=[
        FieldSpec("Return ID", "str", nullable=False),
        FieldSpec("Plant", "str", nullable=False),
        FieldSpec("Month", "int", nullable=False, min_value=0, max_value=239),
        FieldSpec("Return: Volume", "float", nullable=False, min_value=0, max_value=50000),
        FieldSpec("Return: Unit", "str", nullable=False),
    ],
    natural_key=["Return ID"],
    unit_field="Return: Unit",
)

DOWNTIME_LOG = SourceContract(
    source_name="downtime_log",
    is_excel=True,
    expected_columns=["Event ID", "Plant", "Month", "Downtime: Duration", "Downtime: Unit"],
    fields=[
        FieldSpec("Event ID", "str", nullable=False),
        FieldSpec("Plant", "str", nullable=False),
        FieldSpec("Month", "int", nullable=False, min_value=0, max_value=239),
        FieldSpec("Downtime: Duration", "float", nullable=False, min_value=0, max_value=744),
        FieldSpec("Downtime: Unit", "str", nullable=False),
    ],
    natural_key=["Event ID"],
    unit_field="Downtime: Unit",
)

COMPLAINT_TRACKER = SourceContract(
    source_name="complaint_tracker",
    is_excel=True,
    expected_columns=["Complaint ID", "Plant", "Month", "Complaint: Category", "Complaint: Severity"],
    fields=[
        FieldSpec("Complaint ID", "str", nullable=False),
        FieldSpec("Plant", "str", nullable=False),
        FieldSpec("Month", "int", nullable=False, min_value=0, max_value=239),
        FieldSpec("Complaint: Category", "str", nullable=False),
        FieldSpec("Complaint: Severity", "str", nullable=False),
    ],
    natural_key=["Complaint ID"],
    unit_field=None,
)

ERP_ORDER_EXTRACT = SourceContract(
    source_name="erp_order_extract",
    is_excel=False,
    expected_columns=["plant", "month", "return_volume_l_total"],
    fields=[
        FieldSpec("plant", "str", nullable=False),
        FieldSpec("month", "int", nullable=False, min_value=0, max_value=239),
        FieldSpec("return_volume_l_total", "float", nullable=False, min_value=0),
    ],
    natural_key=["plant", "month"],
    expected_countries=[],
)

WMS_SHIPMENT_EXTRACT = SourceContract(
    source_name="wms_shipment_extract",
    is_excel=False,
    expected_columns=["plant", "month", "shipped_kg_total"],
    fields=[
        FieldSpec("plant", "str", nullable=False),
        FieldSpec("month", "int", nullable=False, min_value=0, max_value=239),
        FieldSpec("shipped_kg_total", "float", nullable=False, min_value=0),
    ],
    natural_key=["plant", "month"],
    expected_countries=[],
)

CONTRACTS = {
    "shipment_log": SHIPMENT_LOG,
    "returns_register": RETURNS_REGISTER,
    "downtime_log": DOWNTIME_LOG,
    "complaint_tracker": COMPLAINT_TRACKER,
    "erp_order_extract": ERP_ORDER_EXTRACT,
    "wms_shipment_extract": WMS_SHIPMENT_EXTRACT,
}

assert set(UNIT_CONVERSION.keys()) <= set(CONTRACTS.keys())
