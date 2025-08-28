# test_requester_force_session_mounting.py
# Adjust this import to your package path:

from ao3.requester import Requester, NetworkException

import pytest
import requests
from requests.adapters import HTTPAdapter

# ---- Helpers ----


class DummyAdapter(HTTPAdapter):
    """Adapter that always fails: simulates 'no real network'."""
    def send(self, request, **kwargs):
        """
        Put a request

        :param request:
        :param kwargs:
        :return:
        """
        raise requests.RequestException("boom")


class CountingSession(requests.Session):
    """Session that counts mount() calls and preserves mounted adapters."""
    def __init__(self, *args, **kwargs):
        # Not sure why this is needed... but it is
        self.mount_calls = []

        self.throw_error = False

        # Seems to wipe attrs. For some reason.
        super().__init__(*args, **kwargs)

        self.mount_calls = []

    def mount(self, prefix, adapter):
        """
        Checks the number of calls to mount.

        :param prefix:
        :param adapter:
        :return:
        """

        if self.throw_error:
            raise TypeError("Tried to mount. Forbidden.")

        self.mount_calls.append((prefix, adapter))
        return super().mount(prefix, adapter)

# ---- Tests ----


def test_force_session_is_used_and_not_modified(monkeypatch):
    """
    GIVEN a forced session with DummyAdapter mounted for http/https
    WHEN Requester.get is called with force_session
    THEN Requester must:
        - NOT add/replace adapters on that session
        - raise NetworkException (i.e. wrap RequestException)
    """
    # Late import to make it easier for you to tweak the path:
    r = Requester()

    s = CountingSession()
    dummy_http = DummyAdapter()
    dummy_https = DummyAdapter()

    s.mount("http://", dummy_http)
    s.mount("https://", dummy_https)

    baseline_mounts = list(s.mount_calls)  # 2 entries expected

    with pytest.raises(NetworkException):
        # Any URL is fine; the adapter explodes before network
        r.get("https://archiveofourown.org", force_session=s)

    # Adapters are unchanged (same object identity)
    assert s.adapters["http://"] is dummy_http
    assert s.adapters["https://"] is dummy_https

    # No *extra* mounts happened during the call
    assert s.mount_calls == baseline_mounts, f"Requester modified forced session: {s.mount_calls!r}"


def test_force_session_exact_object_is_used(monkeypatch):
    """
    GIVEN a unique session instance
    WHEN calling Requester.get(force_session=s)
    THEN the very same object must be used (no copying/wrapping)
    """

    r = Requester()

    class SentinelAdapter(HTTPAdapter):
        def send(self, request, **kwargs):
            # We raise to avoid any real I/O; the existence of this call
            # implies this exact session (and adapter) was used.
            raise requests.RequestException("sentinel")

    s = CountingSession()
    sentinel = SentinelAdapter()
    s.mount("https://", sentinel)
    s.mount("http://", sentinel)

    # Before the call, capture object id
    sid_before = id(s)

    with pytest.raises(NetworkException):
        r.get("https://archiveofourown.org/works/123", force_session=s)

    # Ensure the same object came back unmodified
    assert id(s) == sid_before
    assert s.adapters["https://"] is sentinel
    assert s.adapters["http://"] is sentinel


def test_default_session_mounts_adapters(monkeypatch):
    """
    GIVEN no forced session
    WHEN Requester.get is called
    THEN Requester should create its own session and mount adapters (http/https).
    We monkeypatch requests.Session.mount to record calls and prevent real I/O by
    patching requests.Session.request to raise.
    """
    mounted = []

    # Spy on all future Session.mount calls
    original_mount = requests.Session.mount
    def spy_mount(self, prefix, adapter):
        mounted.append((prefix, type(adapter)))
        return original_mount(self, prefix, adapter)

    def boom_request(self, *args, **kwargs):
        # Prevent real network; emulate transient failure
        raise requests.RequestException("no network during test")

    monkeypatch.setattr(requests.Session, "mount", spy_mount, raising=True)
    monkeypatch.setattr(requests.Session, "request", boom_request, raising=True)

    r = Requester()
    with pytest.raises(Exception):
        # We don't assert the exception type here—only that mounts occurred.
        r.get("https://archiveofourown.org")

    # Expect at least http/https mounts; order not guaranteed
    schemes = {prefix for (prefix, _adapter_type) in mounted}
    assert "http://" in schemes and "https://" in schemes, f"No http/https mounts recorded: {mounted!r}"


def test_force_session_survives_retry_wrapper(monkeypatch):
    """
    Some implementations re-wrap the session request with retry logic.
    This test ensures that when force_session is provided, the retry layer
    does NOT swap adapters underneath.
    """
    r = Requester()

    s = CountingSession()

    dummy_http = DummyAdapter()
    dummy_https = DummyAdapter()

    s.mount("http://", dummy_http)
    s.mount("https://", dummy_https)

    assert len(s.mount_calls) == 2, f"Expected exactly two initial mounts, got {s.mount_calls!r}"

    baseline_http = s.adapters["http://"]
    baseline_https = s.adapters["https://"]

    s.throw_error = True

    with pytest.raises(NetworkException):
        r.get("https://archiveofourown.org/series/42", force_session=s)

    # Still the same adapters after retries/backoff handling
    assert s.adapters["http://"] is baseline_http
    assert s.adapters["https://"] is baseline_https

    # And still no extra mount calls
    assert len(s.mount_calls) == 2, f"Expected exactly two initial mounts, got {s.mount_calls!r}"
