"""Exercises the real local cursor-paginated REST API end to end: a real
HTTP server (apiserver.py) bound to a dynamic port, pulled by the real
client (restclient.py) which must follow next_cursor and really sleep
through 429/Retry-After. The server is started and stopped by this test,
by direct object reference, never by PID or process scan.
"""
from reconcilegate import apiserver, restclient


def test_cursor_pagination_and_429_backoff_round_trip():
    records = [{"rate_id": f"R{i:03d}", "v": i} for i in range(37)]
    server, thread = apiserver.start_server(records, page_size=10, fail_every_n=3, retry_after_seconds=0.02)
    try:
        fetched, stats = restclient.fetch_all_pages(server.base_url, "vendor_rate_catalog")
        assert fetched == records
        assert stats["requests"] > 4  # more than ceil(37/10) because of 429s
        assert stats["retries_429"] > 0
        assert stats["total_sleep_s"] > 0
    finally:
        apiserver.stop_server(server, thread)


def test_backoff_actually_sleeps(monkeypatch):
    records = [{"rate_id": f"R{i:03d}"} for i in range(5)]
    server, thread = apiserver.start_server(records, page_size=2, fail_every_n=2, retry_after_seconds=0.05)
    slept = []
    try:
        fetched, stats = restclient.fetch_all_pages(
            server.base_url, "vendor_rate_catalog", max_retries=5, sleep_fn=slept.append
        )
        assert fetched == records
        assert len(slept) > 0
        assert all(s > 0 for s in slept), "a backoff loop that never actually sleeps would show 0-length waits here"
    finally:
        apiserver.stop_server(server, thread)
