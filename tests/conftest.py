"""Fixtures for IntelliDwell Sprinkler Controller tests."""
import threading
import pytest

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations defined in custom_components."""
    yield

@pytest.fixture(autouse=True)
def ignore_safe_shutdown_thread(monkeypatch):
    """Ignore internal Python 3.12 / aiohttp daemon threads in cleanup check."""
    orig_enumerate = threading.enumerate
    def filtered_enumerate():
        return [t for t in orig_enumerate() if "_run_safe_shutdown_loop" not in t.name]
    monkeypatch.setattr(threading, "enumerate", filtered_enumerate)
