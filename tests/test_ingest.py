"""The idempotent-rerun-is-a-no-op property, for all 9 sources, against
the real local PostgreSQL instance (skips cleanly if unreachable, same
pattern as test_db.py).
"""
import pytest

from reconcilegate import config, datagen, db
from reconcilegate.ingest import ingest_source


@pytest.fixture
def conn():
    c = db.try_connect()
    if c is None:
        pytest.skip("PostgreSQL unreachable in this test environment")
    db.ensure_schema(c)
    yield c
    db.reset(c)
    c.close()


@pytest.mark.parametrize("source_name,watermark_col", [
    ("shipment_log", "Month"),
    ("returns_register", "Month"),
    ("downtime_log", "Month"),
    ("complaint_tracker", "Month"),
    ("erp_order_extract", "month"),
    ("wms_shipment_extract", "month"),
    ("vendor_rate_catalog", "cycle"),
    ("vendor_claims_extract", "cycle"),
    ("vendor_directory_feed", "cycle"),
])
def test_rerun_same_cycle_is_a_no_op(conn, source_name, watermark_col):
    cycle = 5
    batch = datagen.generate_clean_batch(config.SEED, cycle)
    payload = batch[source_name]
    if source_name == "vendor_directory_feed":
        payload = payload["rows"]

    first = ingest_source(conn, source_name, payload, cycle)
    assert first.no_op is False
    assert first.rows_new > 0

    second = ingest_source(conn, source_name, payload, cycle)
    assert second.no_op is True
    assert second.rows_new == 0
    assert second.content_hash == first.content_hash
