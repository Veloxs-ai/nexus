# Copyright 2026 Veloxs AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Outbound HTTPS with server-side request forgery (SSRF) protection.

Provider URLs (gateways, ticketing systems, webhooks) are configuration that people type
in, so every call is checked where it matters — after DNS resolution:

  * https only; the host is resolved once and *every* address it resolves to must be allowed
  * never allowed: loopback, link-local (169.254.0.0/16 — cloud metadata — and fe80::/10),
    unspecified, multicast and reserved ranges, including IPv4 hidden in IPv6
    (``::ffff:a.b.c.d``, NAT64 ``64:ff9b::/96``, 6to4 ``2002::/16``)
  * private ranges (RFC 1918, 100.64.0.0/10, fc00::/7) only when allowed: an on-premise
    gateway usually lives there. ``NEXUS_OUTBOUND_ALLOW_PRIVATE=1`` allows them all, or
    ``NEXUS_OUTBOUND_ALLOWED_HOSTS=gw.bank.internal,itsm.bank.internal`` names the hosts
  * the TCP connection goes to the address that was checked (the TLS certificate is still
    verified against the host name), so a DNS answer that changes between the check and
    the connection (DNS rebinding) cannot redirect the call
  * redirects are refused, so an allowed host cannot bounce the request elsewhere

``NEXUS_OUTBOUND_ALLOW_LOOPBACK=1`` allows loopback and plain http to it (local tests only).
"""

from __future__ import annotations

import http.client
import io
import ipaddress
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

MAX_RESPONSE_BYTES = 1 << 20
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


class OutboundBlocked(ValueError):
    """The destination is not allowed (never retried)."""


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def _allowed_hosts() -> set[str]:
    raw = os.environ.get("NEXUS_OUTBOUND_ALLOWED_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _embedded_v4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if ip.ipv4_mapped:
        return ip.ipv4_mapped
    if ip.sixtofour:
        return ip.sixtofour
    if ip in _NAT64:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def check_address(address: str, host: str = "") -> None:
    """Raise OutboundBlocked unless a connection to this IP address is allowed."""
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address):
        inner = _embedded_v4(ip)
        if inner is not None:
            return check_address(str(inner), host)
    if ip.is_loopback:
        if _flag("NEXUS_OUTBOUND_ALLOW_LOOPBACK"):
            return None
        raise OutboundBlocked(f"{host or address}: loopback addresses are not allowed")
    if ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        raise OutboundBlocked(
            f"{host or address}: link-local / metadata / reserved addresses are not allowed"
        )
    private = ip.is_private or (isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT)
    if private and not (_flag("NEXUS_OUTBOUND_ALLOW_PRIVATE") or host.lower() in _allowed_hosts()):
        raise OutboundBlocked(
            f"{host or address} resolves to a private address; allow it with "
            "NEXUS_OUTBOUND_ALLOWED_HOSTS or NEXUS_OUTBOUND_ALLOW_PRIVATE=1"
        )
    return None


def resolve_checked(host: str, port: int) -> str:
    """Resolve and check every address; return the one to connect to."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise OSError(f"cannot resolve {host}: {exc}") from exc
    addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
    if not addresses:
        raise OSError(f"cannot resolve {host}")
    for address in addresses:
        check_address(address, host)
    return addresses[0]


def check_url(url: str) -> None:
    """Static checks usable at configuration time (scheme, and literal IP hosts)."""
    parsed = urllib.parse.urlparse(url)
    loopback_ok = _flag("NEXUS_OUTBOUND_ALLOW_LOOPBACK")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback_ok):
        raise ValueError("provider URLs must use https")
    if not parsed.hostname:
        raise ValueError("provider URL has no host")
    try:
        check_address(parsed.hostname, parsed.hostname)
    except ValueError as exc:
        if isinstance(exc, OutboundBlocked):
            raise
        # not a literal IP: resolved and checked on every call


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float, context: ssl.SSLContext):
        super().__init__(host, port, timeout=timeout, context=context)
        self._address = address

    def connect(self) -> None:
        sock = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class _Response(io.BytesIO):
    def __init__(self, data: bytes, status: int):
        super().__init__(data)
        self.status = status

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def urlopen(request: urllib.request.Request, timeout: float = 10.0) -> _Response:
    """``urllib.request.urlopen``-compatible call with the checks above.

    Raises ``urllib.error.HTTPError`` for 4xx/5xx and refused redirects, ``OutboundBlocked``
    for a destination that is not allowed and ``OSError`` for network failures.
    """
    parsed = urllib.parse.urlparse(request.full_url)
    check_url(request.full_url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    address = resolve_checked(host, port)
    if parsed.scheme == "https":
        conn: http.client.HTTPConnection = _PinnedHTTPSConnection(
            host, port, address, timeout, ssl.create_default_context()
        )
    else:
        conn = _PinnedHTTPConnection(host, port, address, timeout)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    headers = {k: v for k, v in request.header_items()}
    headers.setdefault("Host", parsed.netloc)
    headers.setdefault("User-Agent", "nexus-operations")
    try:
        conn.request(request.get_method(), path, body=request.data, headers=headers)
        response = conn.getresponse()
        body = response.read(MAX_RESPONSE_BYTES)
        status = response.status
        response_headers = response.msg
    finally:
        conn.close()
    if 300 <= status < 400:
        raise urllib.error.HTTPError(
            request.full_url,
            status,
            "redirect refused",
            response_headers,
            io.BytesIO(b"redirect refused"),
        )
    if status >= 400:
        raise urllib.error.HTTPError(
            request.full_url, status, "error", response_headers, io.BytesIO(body[:4096])
        )
    return _Response(body, status)


# Tests replace this with a fake; production code calls ``transport(request, timeout)``.
transport = urlopen
