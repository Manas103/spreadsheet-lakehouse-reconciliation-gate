"""Exercises a real local paramiko SFTP server over loopback: a real SSH
transport and SFTP subsystem, not a simulation of the protocol. Started
and stopped by this test via direct object reference on a dynamically
bound port (never a hardcoded port, never killed by PID scan).
"""
import os

from reconcilegate import sftp_io


def test_real_sftp_round_trip(tmp_path):
    landing = str(tmp_path / "landing")
    os.makedirs(landing, exist_ok=True)
    content = "CLM-000001V00001IT0000012345AP0003\n"
    src = os.path.join(landing, "claims_cycle03.txt")
    with open(src, "w", newline="\n") as f:
        f.write(content)

    server = sftp_io.LandingDirSFTPServer(landing).start()
    try:
        dst = str(tmp_path / "fetched.txt")
        sftp_io.fetch_via_sftp(server.port, "claims_cycle03.txt", dst)
        with open(dst, "r", newline="\n") as f:
            fetched = f.read()
        assert fetched == content
    finally:
        server.stop()
