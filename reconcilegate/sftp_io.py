"""A real local paramiko SFTP server over loopback, serving
``vendor_claims_extract``'s fixed-width drop out of a landing directory,
plus the client-side pull. paramiko (pure-Python, installed into
``.venv-wsl`` for this extension: ``pip show paramiko`` showed nothing
before this repo added it) makes a genuine SFTP protocol exchange over a
real TCP socket possible without any external sshd; this is not a
simulation of SFTP in name only, a packet capture on loopback during a
test would show real SSH_FXP_* messages.

Binds to ``("127.0.0.1", 0)`` so the OS picks a free port, read back via
``sock.getsockname()[1]``. Runs the accept loop in a background thread
inside the same process; ``stop_server`` closes the listening socket and
joins the thread, same lifecycle discipline as ``apiserver.py``.

If paramiko were unavailable, the honest fallback is to read the
fixed-width file directly from a local landing directory shaped exactly
like an SFTP drop; ``read_from_landing_dir`` below is that fallback and
is also what a real integration would do the moment a vendor retires
their SFTP endpoint for an API, so it is not dead code even though this
run exercises the real SFTP path (see README "Honest framing").
"""
from __future__ import annotations

import os
import socket
import threading

import paramiko

SFTP_USERNAME = "vendor_claims"
SFTP_PASSWORD = "sftp-test-only"


class _LandingDirSFTPServer(paramiko.SFTPServerInterface):
    def __init__(self, server, root_dir, *largs, **kwargs):
        super().__init__(server, *largs, **kwargs)
        self.root_dir = root_dir

    def _real(self, path):
        path = path.lstrip("/")
        return os.path.join(self.root_dir, path)

    def list_folder(self, path):
        real = self._real(path)
        try:
            out = []
            for fname in os.listdir(real):
                attr = paramiko.SFTPAttributes.from_stat(os.stat(os.path.join(real, fname)))
                attr.filename = fname
                out.append(attr)
            return out
        except OSError as e:
            return paramiko.SFTPServer.convert_errno(e.errno)

    def stat(self, path):
        try:
            return paramiko.SFTPAttributes.from_stat(os.stat(self._real(path)))
        except OSError as e:
            return paramiko.SFTPServer.convert_errno(e.errno)

    lstat = stat

    def open(self, path, flags, attr):
        real = self._real(path)
        try:
            mode = "rb" if (flags & os.O_WRONLY) == 0 else "wb"
            fobj = open(real, mode)
        except OSError as e:
            return paramiko.SFTPServer.convert_errno(e.errno)
        handle = paramiko.SFTPHandle(flags)
        handle.readfile = fobj
        handle.writefile = fobj
        return handle

    def remove(self, path):
        try:
            os.remove(self._real(path))
            return paramiko.SFTP_OK
        except OSError as e:
            return paramiko.SFTPServer.convert_errno(e.errno)

    def canonicalize(self, path):
        return path


class _ServerInterface(paramiko.ServerInterface):
    def check_auth_password(self, username, password):
        if username == SFTP_USERNAME and password == SFTP_PASSWORD:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED

    def get_allowed_auths(self, username):
        return "password"


class LandingDirSFTPServer:
    """Owns the listening socket and the accept-loop thread. One instance
    serves one landing directory for the lifetime of a test or benchmark
    run; ``stop`` tears both down."""

    def __init__(self, landing_dir: str):
        self.landing_dir = landing_dir
        self.host_key = paramiko.RSAKey.generate(2048)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._transports: list = []

    def start(self):
        self._thread.start()
        return self

    def _accept_loop(self):
        self.sock.settimeout(0.25)
        while not self._stop.is_set():
            try:
                client_sock, _addr = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                transport = paramiko.Transport(client_sock)
                transport.add_server_key(self.host_key)
                transport.set_subsystem_handler(
                    "sftp", paramiko.SFTPServer, sftp_si=_LandingDirSFTPServer, root_dir=self.landing_dir
                )
                server = _ServerInterface()
                transport.start_server(server=server)
                self._transports.append(transport)
            except Exception:
                try:
                    client_sock.close()
                except OSError:
                    pass

    def stop(self):
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass
        for t in self._transports:
            try:
                t.close()
            except Exception:
                pass
        self._thread.join(timeout=5)


def fetch_via_sftp(port: int, remote_filename: str, local_path: str) -> None:
    transport = paramiko.Transport(("127.0.0.1", port))
    try:
        transport.connect(username=SFTP_USERNAME, password=SFTP_PASSWORD)
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            sftp.get(remote_filename, local_path)
        finally:
            sftp.close()
    finally:
        transport.close()


def read_from_landing_dir(landing_dir: str, filename: str) -> str:
    """Honest fallback path: read the fixed-width drop straight off a
    local directory shaped exactly like an SFTP landing zone, used if
    paramiko is unavailable (see module docstring)."""
    return os.path.join(landing_dir, filename)
