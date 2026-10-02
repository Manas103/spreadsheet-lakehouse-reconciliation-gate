"""Runs 20 clean loads and 40 seeded-defect loads (30 in the original
8-type/6-source pool, 10 in the vendor pool: 2 new defect types native to
the 3 new source formats, plus one more instance of an existing type
targeted at a vendor source) through the real materialize -> read -> gate
pipeline, records which checks caught which defect, and publishes/
quarantines each load to PostgreSQL if it is reachable. Writes
docs/benchmark_output.txt.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reconcilegate import config, datagen, db, lakehouse, materialize
from reconcilegate.gate import run_gate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("RECONCILEGATE_DATA_DIR", os.path.join(ROOT, "data"))
LAKEHOUSE_DIR = os.path.join(DATA_DIR, "lakehouse")
DOCS_DIR = os.path.join(ROOT, "docs")


def _expand_defect_instances():
    """Returns [(pool, defect_type, month)], 40 total, each month index
    unique across the whole run for RNG independence (same convention the
    original 30-instance benchmark used)."""
    instances = []
    month = 0
    for defect_type, count in config.DEFECT_COUNTS_ORIGINAL.items():
        for _ in range(count):
            instances.append(("original", defect_type, month))
            month += 1
    for defect_type, count in config.DEFECT_COUNTS_VENDOR.items():
        for _ in range(count):
            instances.append(("vendor", defect_type, month))
            month += 1
    return instances


def main():
    lines = []

    def log(msg):
        print(msg)
        lines.append(msg)

    conn = db.try_connect()
    if conn is not None:
        db.ensure_schema(conn)
        db.reset(conn)
        log("PostgreSQL reachable at 127.0.0.1:5432, database reconcilegate: publishing/quarantining live.")
    else:
        log("PostgreSQL unreachable: gate decisions still measured, nothing published to a live database.")

    spark = lakehouse.build_spark()
    n_lakehouse_writes = 0

    log("")
    log(f"=== {config.N_CLEAN_LOADS} clean loads across {len(config.ALL_SOURCES)} sources ===")
    clean_held = 0
    for month in range(config.N_CLEAN_LOADS):
        batch = datagen.generate_clean_batch(config.SEED, month)
        out_dir = os.path.join(DATA_DIR, f"clean_{month:02d}")
        paths = materialize.write_batch(batch, out_dir)
        sources = materialize.read_batch(paths)
        result = run_gate(f"clean-{month:02d}", sources)
        status = "PUBLISHED" if result.published else "HELD"
        log(f"load clean-{month:02d}: {status} ({len(result.failing_checks)} failing checks)")
        if not result.published:
            clean_held += 1
            for c in result.failing_check_names:
                log(f"    unexpected failing check: {c}")
        else:
            lakehouse.publish_load(spark, sources, month, LAKEHOUSE_DIR)
            n_lakehouse_writes += 1
        if conn is not None:
            if result.published:
                db.publish(conn, result.load_id, month, len(sources))
            else:
                db.quarantine(conn, result.load_id, month, result.failing_check_names)

    log("")
    log(f"clean loads held: {clean_held} of {config.N_CLEAN_LOADS}")

    log("")
    log(f"=== {config.N_SEEDED_DEFECTS} seeded-defect loads, {len(config.DEFECT_COUNTS)} defect types ===")
    instances = _expand_defect_instances()
    assert len(instances) == config.N_SEEDED_DEFECTS
    caught = 0
    per_type_caught = {t: 0 for t in config.DEFECT_COUNTS}
    for pool, defect_type, month in instances:
        batch, defect_source, expected_check = datagen.generate_defect_batch(config.SEED, month, defect_type, pool=pool)
        out_dir = os.path.join(DATA_DIR, f"defect_{pool}_{defect_type}_{month:02d}")
        paths = materialize.write_batch(batch, out_dir)
        sources = materialize.read_batch(paths)
        result = run_gate(f"defect-{pool}-{defect_type}-{month:02d}", sources)
        was_caught = (not result.published) and any(
            c.check == defect_type for c in result.failing_checks
        )
        if was_caught:
            caught += 1
            per_type_caught[defect_type] += 1
        log(
            f"load defect-{pool}-{defect_type}-{month:02d} (expected {expected_check}): "
            f"{'CAUGHT' if was_caught else 'MISSED'}, published={result.published}, "
            f"failing_checks={result.failing_check_names}"
        )
        if result.published:
            lakehouse.publish_load(spark, sources, month, LAKEHOUSE_DIR)
            n_lakehouse_writes += 1
        if conn is not None:
            if result.published:
                db.publish(conn, result.load_id, month, len(sources))
            else:
                db.quarantine(conn, result.load_id, month, result.failing_check_names)

    log("")
    log(f"seeded defects caught: {caught} of {config.N_SEEDED_DEFECTS}")
    log("by defect type:")
    for t, count in config.DEFECT_COUNTS.items():
        log(f"  {t}: {per_type_caught[t]} of {count}")

    if conn is not None:
        conn.close()
    spark.stop()
    log("")
    log(
        f"lakehouse writes (published loads, original 6 sources only, see README Limitations): "
        f"{n_lakehouse_writes} of {config.N_CLEAN_LOADS + config.N_SEEDED_DEFECTS} total loads"
    )

    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "benchmark_output.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    log("")
    log("wrote docs/benchmark_output.txt")


if __name__ == "__main__":
    main()
