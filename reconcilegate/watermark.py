"""Per-source watermark persistence in the same governed PostgreSQL
schema as published_loads/quarantined_loads (``reconcilegate.db``). A
watermark is the highest ``watermark_column`` value (every contract
declares one, see contracts/*.yaml) this source has ever been ingested
through; ``ingest.py`` uses it to make a rerun with no new upstream data
a true no-op.
"""
from __future__ import annotations


def get_watermark(conn, source_name: str):
    with conn.cursor() as cur:
        cur.execute("SELECT last_watermark FROM source_watermarks WHERE source_name = %s", (source_name,))
        row = cur.fetchone()
    return row[0] if row else None


def record_ingest(conn, source_name: str, watermark_value: float, row_count: int, content_hash: str, result: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_watermarks (source_name, last_watermark, last_row_count, last_content_hash, last_result)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source_name) DO UPDATE SET
                last_watermark = EXCLUDED.last_watermark,
                last_row_count = EXCLUDED.last_row_count,
                last_content_hash = EXCLUDED.last_content_hash,
                last_result = EXCLUDED.last_result,
                updated_at = now()
            """,
            (source_name, watermark_value, row_count, content_hash, result),
        )
    conn.commit()
