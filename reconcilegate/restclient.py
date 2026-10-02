"""Real cursor-following pagination and real exponential backoff for
``vendor_rate_catalog``'s REST API (apiserver.py). "Real" backoff means
an actual ``time.sleep`` for a duration computed from both the server's
``Retry-After`` header and our own exponential schedule, not a fixed
``time.sleep(1)`` dressed up as backoff. ``tests/test_apiserver_restclient.py``
asserts every recorded sleep duration is strictly greater than zero,
specifically so a client that silently stopped waiting would fail loudly
instead of merely looking correct.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request


class BackoffExhausted(RuntimeError):
    pass


def fetch_all_pages(
    base_url: str,
    source_name: str,
    max_retries: int = 10,
    base_delay: float = 0.01,
    max_delay: float = 2.0,
    timeout: float = 5.0,
    sleep_fn=time.sleep,
) -> tuple:
    """Returns (records, stats) where stats carries how many 429s were
    hit and the total time actually spent sleeping, so a test can assert
    backoff really happened rather than merely that the final result is
    correct.
    """
    records: list = []
    cursor = None
    retries = 0
    stats = {"requests": 0, "retries_429": 0, "total_sleep_s": 0.0}

    while True:
        url = f"{base_url}/{source_name}"
        if cursor is not None:
            url += "?" + urllib.parse.urlencode({"cursor": cursor})

        stats["requests"] += 1
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            retries += 1
            stats["retries_429"] += 1
            if retries > max_retries:
                raise BackoffExhausted(
                    f"gave up pulling {source_name} after {max_retries} retries on 429"
                ) from e
            retry_after_header = e.headers.get("Retry-After")
            server_wait = float(retry_after_header) if retry_after_header is not None else 0.0
            exponential_wait = min(max_delay, base_delay * (2 ** (retries - 1)))
            wait = max(server_wait, exponential_wait)
            stats["total_sleep_s"] += wait
            sleep_fn(wait)
            continue

        records.extend(payload["records"])
        retries = 0
        cursor = payload.get("next_cursor")
        if cursor is None:
            break

    return records, stats
