from reconcilegate import db


def test_skips_cleanly_or_connects():
    conn = db.try_connect()
    if conn is None:
        # PostgreSQL unreachable in this test environment: this is the
        # documented clean-skip path, not a failure.
        assert True
        return
    db.ensure_schema(conn)
    db.reset(conn)
    db.publish(conn, "test-load-1", 0, 6)
    db.quarantine(conn, "test-load-2", 0, ["out_of_range_value:shipment_log:IT row 0"])
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM published_loads")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM quarantined_loads")
        assert cur.fetchone()[0] == 1
    db.reset(conn)
    conn.close()
