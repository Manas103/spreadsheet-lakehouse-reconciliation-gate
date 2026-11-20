"""Reproducible measures report: renders the four legacy reports from the
9 measure definitions over one clean load, then runs the "Shipments This
Period" comparison across the 3 deliberate duplicate-Order-ID scenarios
(reconcilegate.measures_fixtures) and one genuinely clean load, to show
both the disagreement and that it does not fire where there is nothing to
find.

Run: python scripts/run_measures_report.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reconcilegate import measures
from reconcilegate.config import SEED
from reconcilegate.datagen import generate_clean_batch
from reconcilegate.measures_fixtures import build_duplicate_scenarios


def main():
    sample_batch = generate_clean_batch(SEED, month=10)
    rendered = measures.render_reports(sample_batch)

    n_measures = sum(len(v) for v in rendered.values())
    print(f"Rendered {len(rendered)} reports from {n_measures} measure definitions "
          f"(month 10, clean load):")
    for report_name, values in rendered.items():
        print(f"  {report_name}:")
        for measure_name, per_plant in values.items():
            print(f"    {measure_name}: {per_plant}")

    print()
    print("Shipments This Period disagreement check, 3 deliberate duplicate-Order-ID scenarios:")
    total_disagreements = 0
    for month, batch in build_duplicate_scenarios():
        found = measures.find_shipments_this_period_disagreements(batch)
        total_disagreements += len(found)
        print(f"  month {month}: {len(found)} disagreement(s)")
        for d in found:
            print(f"    plant={d['plant']} shipment_performance={d['shipment_performance_report_value']} "
                  f"returns_and_quality={d['returns_and_quality_report_value']}")
            print(f"    definition_difference: {d['definition_difference']}")

    print(f"TOTAL DISAGREEMENTS FOUND: {total_disagreements} of 3 scenarios")

    false_positives = 0
    for month in range(20):
        clean_batch = generate_clean_batch(SEED, month=month)
        false_positives += len(measures.find_shipments_this_period_disagreements(clean_batch))
    print(f"False-positive check across 20 independent clean loads (months 0-19): "
          f"{false_positives} disagreement(s)")


if __name__ == "__main__":
    main()
