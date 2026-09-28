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

"""Outbound calls: SSRF checks after DNS resolution, pinned address, no redirects."""

import http.server
import socket
import threading
import urllib.error
import urllib.request

import pytest

from nexus.operations import outbound
from nexus.operations.messaging import WebhookProvider


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
        "0.0.0.0",
        "::ffff:169.254.169.254",
        "64:ff9b::a9fe:a9fe",
        "2002:a9fe:a9fe::1",
        "224.0.0.1",
    ],
)
def test_never_allowed(address, monkeypatch):
    monkeypatch.setenv("NEXUS_OUTBOUND_ALLOW_PRIVATE", "1")
    with pytest.raises(outbound.OutboundBlocked):
        outbound.check_address(address, "gw.example")


def test_private_only_when_allowed(monkeypatch):
    for env in ("NEXUS_OUTBOUND_ALLOW_PRIVATE", "NEXUS_OUTBOUND_ALLOWED_HOSTS"):
        monkeypatch.delenv(env, raising=False)
    with pytest.raises(outbound.OutboundBlocked, match="private"):
        outbound.check_address("10.1.2.3", "gw.bank.internal")
    monkeypatch.setenv("NEXUS_OUTBOUND_ALLOWED_HOSTS", "gw.bank.internal")
    outbound.check_address("10.1.2.3", "gw.bank.internal")
    with pytest.raises(outbound.OutboundBlocked):
        outbound.check_address("10.1.2.3", "other.bank.internal")
    outbound.check_address("93.184.216.34", "example.com")  # public


def test_every_resolved_address_is_checked(monkeypatch):
    """A public name that (also) resolves to the metadata address is refused (DNS tricks)."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, type=0: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port)),
        ],
    )
    with pytest.raises(outbound.OutboundBlocked):
        outbound.resolve_checked("169-254-169-254.nip.io", 443)


def test_provider_refuses_metadata_url_at_configuration():
    with pytest.raises(outbound.OutboundBlocked):
        WebhookProvider("https://169.254.169.254/latest", "0123456789abcdef0123")


def test_blocked_destination_is_a_permanent_failure(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, type=0: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))
        ],
    )
    monkeypatch.delenv("NEXUS_OUTBOUND_ALLOW_PRIVATE", raising=False)
    from nexus.operations import Message

    result = WebhookProvider("https://gw.example", "0123456789abcdef0123").send(
        Message(channel="sms", to="+910000000000", body="hi", idempotency_key="k")
    )
    assert not result.ok and not result.retryable and "not allowed" in result.error


def test_redirects_are_refused_and_responses_read(monkeypatch):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            if self.path == "/moved":
                self.send_response(302)
                self.send_header("Location", "http://169.254.169.254/")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("NEXUS_OUTBOUND_ALLOW_LOOPBACK", "1")
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        ok = outbound.urlopen(
            urllib.request.Request(base + "/ok", data=b"{}", method="POST"), timeout=5
        )
        assert ok.read() == b'{"ok": true}' and ok.status == 200
        with pytest.raises(urllib.error.HTTPError) as err:
            outbound.urlopen(
                urllib.request.Request(base + "/moved", data=b"{}", method="POST"), timeout=5
            )
        assert err.value.code == 302
    finally:
        server.shutdown()
    monkeypatch.delenv("NEXUS_OUTBOUND_ALLOW_LOOPBACK")
    with pytest.raises(ValueError):
        outbound.urlopen(urllib.request.Request(base + "/ok", data=b"{}", method="POST"), timeout=5)


def test_smtp_connects_to_the_checked_address(monkeypatch):
    """The mail host is resolved once, checked, and the TCP connection goes to that address."""
    import smtplib

    connected = []
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, type=0: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))
        ],
    )

    def fake_connection(address, timeout=None, source_address=None):
        connected.append(address)
        raise ConnectionRefusedError("stop here")

    monkeypatch.setattr(socket, "create_connection", fake_connection)
    import ssl

    with pytest.raises(ConnectionRefusedError):
        outbound.pinned_smtp(
            "mail.example.com",
            587,
            implicit_tls=False,
            timeout=5,
            context=ssl.create_default_context(),
        )
    assert connected == [("93.184.216.34", 587)]
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, type=0: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port))
        ],
    )
    with pytest.raises(outbound.OutboundBlocked):
        outbound.pinned_smtp(
            "mail.example.com",
            587,
            implicit_tls=False,
            timeout=5,
            context=ssl.create_default_context(),
        )
    assert smtplib  # imported lazily by pinned_smtp
