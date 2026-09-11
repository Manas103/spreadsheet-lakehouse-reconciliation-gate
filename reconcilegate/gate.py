"""The fail-closed gate: run every source's contract, then reconciliation
for the two sources that have a system-of-record, and quarantine the
whole load (do not publish anything) if any check anywhere failed. A
load is all-or-nothing: this repo does not partially publish a load with
one bad source and five good ones, because a partially-published load is
exactly the silent-corruption failure mode a reconciliation gate exists
to prevent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from reconcilegate.config import RECONCILIATION_TARGETS
from reconcilegate.contracts import CONTRACTS
from reconcilegate.reconcile import reconcile_source
from reconcilegate.validate import FailingCheck, validate_excel_source, validate_flat_source

EXCEL_SOURCES = ["shipment_log", "returns_register", "downtime_log", "complaint_tracker"]
FLAT_SOURCES = ["erp_order_extract", "wms_shipment_extract"]


@dataclass
class GateResult:
    load_id: str
    published: bool
    failing_checks: list = field(default_factory=list)

    @property
    def failing_check_names(self) -> list:
        return [str(c) for c in self.failing_checks]


def run_gate(load_id: str, sources: dict) -> GateResult:
    failing: list[FailingCheck] = []

    for source in EXCEL_SOURCES:
        failing.extend(validate_excel_source(sources[source], CONTRACTS[source]))
    for source in FLAT_SOURCES:
        failing.extend(validate_flat_source(sources[source], CONTRACTS[source]))

    # Reconciliation only for a source whose own contract checks passed
    # (a header/type failure makes a computed total meaningless), and only
    # if its target system-of-record source also passed its own checks.
    already_failing_sources = {c.source for c in failing}
    for source, target in RECONCILIATION_TARGETS.items():
        if source in already_failing_sources or target["sor_source"] in already_failing_sources:
            continue
        failing.extend(reconcile_source(source, sources[source], sources[target["sor_source"]]))

    return GateResult(load_id=load_id, published=(len(failing) == 0), failing_checks=failing)
