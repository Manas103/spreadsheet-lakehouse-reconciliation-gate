"""A deliberate, disclosed 3-scenario fixture for the "Shipments This
Period" disagreement: 3 clean loads (months 200, 201, 202, still inside the
contract's declared 0-239 range but far above the roughly 0-39 range the
main 20-clean/40-defect benchmark actually uses, so this never collides
with it), each with exactly one shipment_log row's Order ID duplicated in
one plant's sheet. This is not the main benchmark generator; it exists
only to demonstrate and measure the one definition-difference finding
this extension reports.
"""
import numpy as np
import pandas as pd

from reconcilegate.config import SEED
from reconcilegate.datagen import generate_clean_batch

DUPLICATE_SCENARIO_MONTHS = [200, 201, 202]


def _duplicate_one_order_id(shipment_sheets: dict, month: int) -> dict:
    rng = np.random.default_rng(abs(hash((SEED, month, "dup-fixture"))) % (2**32))
    country = str(rng.choice(list(shipment_sheets.keys())))
    sheets = {**shipment_sheets}
    df = sheets[country].copy()
    dup_row = df.iloc[[0]].copy()
    dup_row["Order ID"] = df.iloc[1]["Order ID"]  # collide with an existing key
    sheets[country] = pd.concat([df, dup_row], ignore_index=True)
    return sheets


def build_duplicate_scenarios():
    """Returns a list of (month, batch) for the 3 scenarios, each batch's
    shipment_log sheets carrying exactly one duplicated Order ID."""
    scenarios = []
    for month in DUPLICATE_SCENARIO_MONTHS:
        batch = generate_clean_batch(SEED, month)
        batch = {**batch, "shipment_log": _duplicate_one_order_id(batch["shipment_log"], month)}
        scenarios.append((month, batch))
    return scenarios
