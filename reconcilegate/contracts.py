"""Loads every source's contract from a real per-source YAML file under
``contracts/`` into a ``SourceContract`` object. This used to be 6 Python
module-level dataclass literals; the "a per-source YAML contract" claim
this repo now makes is true for all 9 sources, not just the 3 added for
it, so all 9 (including the original 6, unchanged in meaning) were moved
to YAML in the same refactor. ``validate.py``, ``gate.py``, ``reconcile.py``
still see the same ``SourceContract``/``FieldSpec`` objects as before;
only where they come from changed.

A field's shape for a non-fixed-width source is unaffected by the extra
attributes (``start``, ``length``, ``pattern``, ``aliases``, ``required``)
added for the 3 new source kinds; they default to ``None`` / ``[]`` / ``True``
and are simply unused by the excel/csv validators.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

import yaml

from reconcilegate.config import COUNTRIES, UNIT_CONVERSION

CONTRACTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    dtype: str  # "str", "int", "float", "bool_yn"
    nullable: bool = False
    min_value: float | None = None
    max_value: float | None = None
    # fixed_width only: this field's byte offset and length in the record.
    start: int | None = None
    length: int | None = None
    # fixed_width only: a regex the sliced raw value must fullmatch; a
    # mismatch here means the declared byte offsets no longer line up
    # with this field's actual content (fixed_width_field_misaligned).
    pattern: str | None = None
    # drifting_csv only: alternate header names this field is recognized
    # under across drops (e.g. "tax_id" drifting to "tin").
    aliases: tuple = ()
    # drifting_csv only: whether this column must appear (by name or
    # alias) in every drop. False means "may be absent", not "may be null".
    required: bool = True


@dataclass(frozen=True)
class SourceContract:
    source_name: str
    kind: str  # "excel" | "csv" | "rest_api" | "fixed_width" | "drifting_csv"
    expected_columns: list
    fields: list  # list[FieldSpec]
    natural_key: list
    owner: str
    watermark_column: str
    refresh_window_hours: float
    late_arrival_window_hours: float
    expected_countries: list = field(default_factory=lambda: list(COUNTRIES))
    unit_field: str | None = None
    record_length: int | None = None  # fixed_width only
    extra: dict = field(default_factory=dict)  # kind-specific config (e.g. api.page_size)

    @property
    def is_excel(self) -> bool:
        return self.kind == "excel"

    def field(self, name: str) -> FieldSpec:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(f"{self.source_name}: no field named {name!r}")


_KNOWN_TOP_LEVEL_KEYS = {
    "source_name",
    "kind",
    "owner",
    "watermark_column",
    "refresh_window_hours",
    "late_arrival_window_hours",
    "expected_countries",
    "unit_field",
    "natural_key",
    "expected_columns",
    "fields",
    "record_length",
}


def _load_field(raw: dict) -> FieldSpec:
    return FieldSpec(
        name=raw["name"],
        dtype=raw["dtype"],
        nullable=bool(raw.get("nullable", False)),
        min_value=raw.get("min_value"),
        max_value=raw.get("max_value"),
        start=raw.get("start"),
        length=raw.get("length"),
        pattern=raw.get("pattern"),
        aliases=tuple(raw.get("aliases", [])),
        required=bool(raw.get("required", True)),
    )


def load_contract(path: str) -> SourceContract:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    missing = {"source_name", "kind", "expected_columns", "fields", "natural_key"} - set(raw)
    if missing:
        raise ValueError(f"{path}: contract YAML missing required keys {sorted(missing)}")

    fields = [_load_field(r) for r in raw["fields"]]
    declared_field_names = {f.name for f in fields}
    expected = set(raw["expected_columns"])
    if not expected <= declared_field_names:
        raise ValueError(
            f"{path}: expected_columns names {sorted(expected - declared_field_names)} "
            "have no matching entry under fields: (a YAML contract silently dropping a "
            "field during the refactor is exactly the bug this check exists to catch)"
        )

    extra = {k: v for k, v in raw.items() if k not in _KNOWN_TOP_LEVEL_KEYS}

    return SourceContract(
        source_name=raw["source_name"],
        kind=raw["kind"],
        expected_columns=list(raw["expected_columns"]),
        fields=fields,
        natural_key=list(raw["natural_key"]),
        owner=raw.get("owner", ""),
        watermark_column=raw.get("watermark_column", ""),
        refresh_window_hours=float(raw.get("refresh_window_hours", 24.0)),
        late_arrival_window_hours=float(raw.get("late_arrival_window_hours", 24.0)),
        expected_countries=list(raw.get("expected_countries", [])),
        unit_field=raw.get("unit_field"),
        record_length=raw.get("record_length"),
        extra=extra,
    )


def _load_all_contracts(contracts_dir: str = CONTRACTS_DIR) -> dict:
    contracts = {}
    for path in sorted(glob.glob(os.path.join(contracts_dir, "*.yaml"))):
        contract = load_contract(path)
        contracts[contract.source_name] = contract
    return contracts


CONTRACTS = _load_all_contracts()

# Convenience accessors used across the codebase (unchanged names from the
# pre-YAML module so other modules importing a specific constant still work).
SHIPMENT_LOG = CONTRACTS.get("shipment_log")
RETURNS_REGISTER = CONTRACTS.get("returns_register")
DOWNTIME_LOG = CONTRACTS.get("downtime_log")
COMPLAINT_TRACKER = CONTRACTS.get("complaint_tracker")
ERP_ORDER_EXTRACT = CONTRACTS.get("erp_order_extract")
WMS_SHIPMENT_EXTRACT = CONTRACTS.get("wms_shipment_extract")
VENDOR_RATE_CATALOG = CONTRACTS.get("vendor_rate_catalog")
VENDOR_CLAIMS_EXTRACT = CONTRACTS.get("vendor_claims_extract")
VENDOR_DIRECTORY_FEED = CONTRACTS.get("vendor_directory_feed")

assert set(UNIT_CONVERSION.keys()) <= set(CONTRACTS.keys())
