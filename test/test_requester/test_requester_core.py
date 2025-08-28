
import pytest
import requests
from ao3.requester import Requester
from ao3.errors import NetworkException, RateLimitedException


def test_init_strict_kwargs():
    """
    Tests init.

    :return:
    """
    with pytest.raises(TypeError):
        Requester(window_seconds=10, bad_kwarg=True)


def test_request_strict_kwargs():
    """
    Tests the requester with a known bad kwarg - should fail.

    :return:
    """
    r = Requester()
    with pytest.raises(TypeError):
        r.request("GET", "https://example.com", bad_kwarg=True)


def test_configure_session_idempotent():
    r = Requester()
    s = requests.Session()
    r.configure_session(s)
    assert getattr(s, "_ao3_adapters_installed", False)
    assert getattr(s, "_ao3_headers_installed", False)
    r.configure_session(s)
    assert getattr(s, "_ao3_adapters_installed", False)


def test_headers_respect_existing():
    """
    Tests our default headers are replaced when using an internal session.

    :return:
    """
    r = Requester(user_agent="ao3.py/override")
    s = requests.Session()
    s.headers["User-Agent"] = "my-app/1.0"
    r.configure_session(s)
    assert s.headers["User-Agent"] == "my-app/1.0"


class DummyAdapter(requests.adapters.HTTPAdapter):
    """
    Do not want to actually do internet IO.
    """
    def send(self, request, **kwargs):
        """
        Should fail on any actual call.

        :param request:
        :param kwargs:
        :return:
        """
        raise requests.RequestException("boom")


def test_network_exception():
    """
    Tests a known NetworkException is thrown when the network is borked.

    :return:
    """
    r = Requester()
    s = requests.Session()

    s.mount("http://", DummyAdapter())
    s.mount("https://", DummyAdapter())

    with pytest.raises(NetworkException):
        resp = r.get("https://archiveofourown.org", force_session=s)
        assert resp.raw



def test_429_rate_limited(monkeypatch):

    r = Requester()
    s = requests.Session()

    class Resp:
        status_code = 429
        headers = {"Retry-After": "2"}
        url = "https://example.com"

    s.request = lambda *a, **k: Resp()

    with pytest.raises(RateLimitedException) as ei:
        r.get("https://archiveofourown.org", force_session=s)

    assert ei.value.retry_after == 2.0
