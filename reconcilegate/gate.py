"""The fail-closed gate: run every source's contract (dispatched by the
contract's own declared ``kind``, not a hardcoded source list, so adding
a 10th source means adding a contract, not editing this file), then
reconciliation for the two sources that have a system-of-record, and
quarantine the whole load (do not publish anything) if any check anywhere
failed. A load is all-or-nothing: this repo does not partially publish a
load with one bad source and eight good ones, because a partially-
published load is exactly the silent-corruption failure mode a
reconciliation gate exists to prevent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from reconcilegate.config import RECONCILIATION_TARGETS
from reconcilegate.contracts import CONTRACTS
from reconcilegate.drifting_csv import validate_drifting_csv_source
from reconcilegate.fixedwidth import validate_fixed_width_source
from reconcilegate.reconcile import reconcile_source
from reconcilegate.validate import FailingCheck, validate_excel_source, validate_flat_source


@dataclass
class GateResult:
    load_id: str
    published: bool
    failing_checks: list = field(default_factory=list)

    @property
    def failing_check_names(self) -> list:
        return [str(c) for c in self.failing_checks]


def _validate_one_source(name: str, sources: dict) -> list:
    contract = CONTRACTS[name]
    if contract.kind == "excel":
        return validate_excel_source(sources[name], contract)
    if contract.kind in ("csv", "rest_api"):
        return validate_flat_source(sources[name], contract)
    if contract.kind == "fixed_width":
        return validate_fixed_width_source(sources[name], contract)
    if contract.kind == "drifting_csv":
        return validate_drifting_csv_source(sources[name], contract)
    raise ValueError(f"{name}: unknown contract kind {contract.kind!r}")


def run_gate(load_id: str, sources: dict) -> GateResult:
    failing: list[FailingCheck] = []

    for name in CONTRACTS:
        failing.extend(_validate_one_source(name, sources))

    # Reconciliation only for a source whose own contract checks passed
    # (a header/type failure makes a computed total meaningless), and only
    # if its target system-of-record source also passed its own checks.
    already_failing_sources = {c.source for c in failing}
    for source, target in RECONCILIATION_TARGETS.items():
        if source in already_failing_sources or target["sor_source"] in already_failing_sources:
            continue
        failing.extend(reconcile_source(source, sources[source], sources[target["sor_source"]]))

    return GateResult(load_id=load_id, published=(len(failing) == 0), failing_checks=failing)
