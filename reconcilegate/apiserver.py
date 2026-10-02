"""A real local HTTP server for ``vendor_rate_catalog``, stdlib
``http.server`` only (no Flask/FastAPI in this venv, and stdlib is
plenty for one cursor-paginated endpoint). Binds to ``("127.0.0.1", 0)``
so the OS picks a free port, which the caller reads back from
``server.server_address[1]``; nothing here ever hardcodes a port.

Runs as a background thread inside the same process that started it, not
a separate OS process: there is no PID to track or kill, no port to
collide with a previous run, and ``stop_server`` leaves nothing behind
when it returns. A test or benchmark run starts its own server instance
and stops it in the same function, by direct object reference, before
moving on, exactly as the fixed-width/SFTP side of this repo also does
with its paramiko server (see ``sftp_io.py``).

A fixed fraction of requests return HTTP 429 with a ``Retry-After``
header and no body, simulating a vendor API with real rate limiting;
``restclient.py`` is what has to actually honor that.
"""
from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A003 - silence per-request logging
        pass

    def do_GET(self):
        server: VendorApiServer = self.server  # type: ignore[assignment]
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != f"/{server.source_name}":
            self._send_json(404, {"error": "not found"})
            return

        qs = urllib.parse.parse_qs(parsed.query)
        cursor = int(qs.get("cursor", ["0"])[0])

        server.request_count += 1
        if server.fail_every_n and server.request_count % server.fail_every_n == 0:
            self.send_response(429)
            self.send_header("Retry-After", str(server.retry_after_seconds))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        page = server.records[cursor : cursor + server.page_size]
        next_cursor = cursor + server.page_size
        if next_cursor >= len(server.records):
            next_cursor = None
        self._send_json(200, {"records": page, "next_cursor": next_cursor})

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class VendorApiServer(HTTPServer):
    def __init__(
        self,
        records: list,
        source_name: str = "vendor_rate_catalog",
        page_size: int = 10,
        fail_every_n: int = 3,
        retry_after_seconds: float = 0.05,
    ):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.records = records
        self.source_name = source_name
        self.page_size = page_size
        self.fail_every_n = fail_every_n
        self.retry_after_seconds = retry_after_seconds
        self.request_count = 0

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


def start_server(records: list, **kwargs) -> tuple:
    server = VendorApiServer(records, **kwargs)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    return server, thread


def stop_server(server: VendorApiServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
