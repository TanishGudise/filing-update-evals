"""The network guard: in-process (this test session) and around a whole process tree."""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import pytest

from filing_update_evals.netguard import NetworkBlocked

REPO = Path(__file__).resolve().parent.parent


def test_in_process_guard_blocks_everything_but_loopback():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    socket.create_connection(server.getsockname(), timeout=2).close()
    server.close()
    with pytest.raises(NetworkBlocked):
        socket.getaddrinfo("www.sec.gov", 443)
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("1.1.1.1", 443), timeout=2)
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("2606:4700:4700::1111", 443), timeout=2)


PROBE = """
import socket
def attempt(fn):
    try:
        fn()
        return "open"
    except Exception as exc:
        return type(exc).__name__
server = socket.socket(); server.bind(("127.0.0.1", 0)); server.listen(1)
print(attempt(lambda: socket.create_connection(server.getsockname(), timeout=2).close()))
print(attempt(lambda: socket.getaddrinfo("www.sec.gov", 443)))
print(attempt(lambda: socket.create_connection(("1.1.1.1", 443), timeout=2).close()))
"""


@pytest.mark.skipif(sys.platform != "darwin", reason="scripts/guarded uses macOS sandbox-exec")
def test_guarded_blocks_a_whole_process_without_python_help():
    # -I: no sitecustomize, so only the sandbox stands between this process and the network.
    out = subprocess.run(
        [str(REPO / "scripts" / "guarded"), sys.executable, "-I", "-c", PROBE],
        capture_output=True,
        text=True,
        timeout=60,
    )
    loopback, dns, outside = out.stdout.split()
    assert loopback == "open"
    assert dns != "open" and outside != "open"


def test_deadline_kills_the_process_group():
    out = subprocess.run(
        [str(REPO / "scripts" / "deadline"), "1", "sh", "-c", "sleep 30 & sleep 30"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert out.returncode == 124
