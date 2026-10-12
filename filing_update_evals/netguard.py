"""Refuse network connections that leave this machine.

Everything in this repo that reads filings, builds workbooks, grades or runs tests works offline.
`install()` patches the socket module so that a connection to anything but loopback (or a Unix
socket) raises, and name lookups fail for every host except loopback names. Hosts passed in
`allow` (for example the SEC hosts in scripts/fetch.py, or a model API host for paid runs) are
let through, together with the addresses they resolve to.

This is the in-process half of the guard. scripts/guarded adds the out-of-process half: a macOS
sandbox profile that blocks outbound IP traffic and DNS for the whole process tree, including
LibreOffice and anything written in C.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import threading

_LOOPBACK_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}

SANDBOX_PROFILE = """(version 1)
(allow default)
; Loopback only: no outbound IP traffic except to this machine, and no DNS.
(deny network-outbound)
(allow network-outbound (remote ip "localhost:*"))
(allow network-outbound (remote unix-socket))
(deny network-outbound (literal "/private/var/run/mDNSResponder"))
"""
"""The macOS sandbox profile scripts/guard/loopback.sb holds, and recalc.py wraps LibreOffice in
when FUE_SANDBOX_SOFFICE=1 (agent runs, whose own process may reach a model API)."""

_lock = threading.Lock()
_installed = False
_allowed_hosts: set[str] = set()
_allowed_ips: set[str] = set()


class NetworkBlocked(OSError):
    pass


def _is_loopback(host: object) -> bool:
    if not isinstance(host, str):
        return False
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _check_address(family: int, address: object) -> None:
    if family == getattr(socket, "AF_UNIX", object()):
        return
    host = address[0] if isinstance(address, tuple) and address else address
    if _is_loopback(host) or host in _allowed_ips:
        return
    raise NetworkBlocked(f"network guard: connection to {host!r} blocked (loopback only)")


def install(allow: tuple[str, ...] | list[str] = ()) -> None:
    """Patch the socket module once per process. Later calls can only add allowed hosts."""
    global _installed
    with _lock:
        _allowed_hosts.update(h.lower() for h in allow)
        if _installed:
            return
        _installed = True

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    original_gethostbyname = socket.gethostbyname
    original_gethostbyname_ex = socket.gethostbyname_ex

    def connect(self, address):
        _check_address(self.family, address)
        return original_connect(self, address)

    def connect_ex(self, address):
        _check_address(self.family, address)
        return original_connect_ex(self, address)

    def getaddrinfo(host, *args, **kwargs):
        name = host.decode() if isinstance(host, bytes) else host
        if name is None or _is_loopback(name):
            return original_getaddrinfo(host, *args, **kwargs)
        if isinstance(name, str) and name.lower() in _allowed_hosts:
            infos = original_getaddrinfo(host, *args, **kwargs)
            with _lock:
                _allowed_ips.update(info[4][0] for info in infos)
            return infos
        raise NetworkBlocked(f"network guard: lookup of {name!r} blocked (loopback only)")

    def gethostbyname(host):
        if _is_loopback(host):
            return original_gethostbyname(host)
        raise NetworkBlocked(f"network guard: lookup of {host!r} blocked (loopback only)")

    def gethostbyname_ex(host):
        if _is_loopback(host):
            return original_gethostbyname_ex(host)
        raise NetworkBlocked(f"network guard: lookup of {host!r} blocked (loopback only)")

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = getaddrinfo
    socket.gethostbyname = gethostbyname
    socket.gethostbyname_ex = gethostbyname_ex


def install_from_env() -> None:
    """Used by scripts/guard/sitecustomize.py: FUE_NETWORK_GUARD=loopback turns the guard on."""
    if os.environ.get("FUE_NETWORK_GUARD") == "loopback":
        install()
