from __future__ import annotations

import pytest

from opencad_server.http_kernel_client import HttpKernelClient, kernel_base_url


def test_base_url_does_not_duplicate_gateway_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCAD_KERNEL_URL", "http://127.0.0.1:8000/kernel")
    assert kernel_base_url() == "http://127.0.0.1:8000/kernel"


def test_base_url_adds_gateway_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCAD_KERNEL_URL", "http://127.0.0.1:8000")
    assert kernel_base_url() == "http://127.0.0.1:8000/kernel"


def test_base_url_ignores_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCAD_KERNEL_URL", "http://127.0.0.1:8000/kernel/")
    assert kernel_base_url() == "http://127.0.0.1:8000/kernel"


def test_client_resolves_base_url_at_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCAD_KERNEL_URL", "http://kernel.internal:9000")
    assert HttpKernelClient().base_url == "http://kernel.internal:9000/kernel"


def test_client_accepts_explicit_base_url() -> None:
    assert HttpKernelClient("http://elsewhere:1234/kernel/").base_url == "http://elsewhere:1234/kernel"


def test_client_satisfies_the_kernel_client_protocol() -> None:
    from opencad.kernel.client import KernelClient

    assert isinstance(HttpKernelClient("http://127.0.0.1:8000/kernel"), KernelClient)


def test_configured_remote_kernel_client(monkeypatch) -> None:
    """Preserve explicit standalone HTTP kernel wiring."""
    from opencad_server.http_kernel_client import configured_kernel_client

    monkeypatch.setenv("OPENCAD_AGENT_LIVE_KERNEL", "true")
    monkeypatch.setenv("OPENCAD_KERNEL_URL", "http://kernel.internal:9000")
    client = configured_kernel_client("OPENCAD_AGENT_LIVE_KERNEL")
    assert isinstance(client, HttpKernelClient)
    assert client.base_url == "http://kernel.internal:9000/kernel"
