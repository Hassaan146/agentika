"""SSRF guard tests for the page-fetch tool.

Unrestricted server-side fetch of an attacker-influenced URL is the classic
path to the cloud metadata endpoint (169.254.169.254) and internal hosts. These
tests pin the guard: scheme allowlist, blocked address ranges, and re-validation
across a redirect.
"""

import socket

from models import FetchPageInput
from tools import search
from tools.search import _ssrf_reason


def _fake_gai(ip):
    return lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))]


def test_rejects_non_http_scheme():
    assert "http(s)" in _ssrf_reason("file:///etc/passwd")
    assert _ssrf_reason("ftp://example.com/x")


def test_blocks_cloud_metadata_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai("169.254.169.254"))
    reason = _ssrf_reason("http://metadata.example/latest/meta-data/")
    assert reason and "non-public" in reason


def test_blocks_localhost(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai("127.0.0.1"))
    assert _ssrf_reason("http://localhost:8010/")


def test_blocks_private_range(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai("10.0.0.5"))
    assert _ssrf_reason("http://internal.corp/")


def test_allows_public_host(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai("93.184.216.34"))
    assert _ssrf_reason("https://example.com/") is None


class _FakeResp:
    def __init__(self, redirect_to=None, text=""):
        self.is_redirect = redirect_to is not None
        self.text = text
        self.next_request = type("R", (), {"url": redirect_to})() if redirect_to else None

    def raise_for_status(self):
        pass


def test_fetch_page_blocks_redirect_to_internal(monkeypatch):
    """A public URL that 302s to the metadata endpoint is refused at the hop."""

    def fake_get(url, **kwargs):
        return _FakeResp(redirect_to="http://169.254.169.254/latest/meta-data/")

    def fake_gai(host, *a, **k):
        ip = "93.184.216.34" if host == "example.com" else "169.254.169.254"
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))]

    monkeypatch.setattr(search.httpx, "get", fake_get)
    monkeypatch.setattr(socket, "getaddrinfo", fake_gai)

    result = search.fetch_page(FetchPageInput(url="https://example.com"))
    assert not result.ok and "169.254.169.254" in result.error
