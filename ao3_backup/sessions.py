
"""
Contains network sessions for interacting with the archive.
"""

from __future__ import annotations

import time
import random
import requests
from ao3.requester import Requester
from ao3.session.ao3session import GuestAo3Session
from ao3.works import Work

from ao3_backup.config import USER_AGENT, GUEST_DELAY_S, AUTH_DELAY_S, JITTER_S

_req_guest = Requester(
    user_agent=USER_AGENT, requests_per_window=60, window_seconds=60.0
)


def jitter(base: float) -> float:
    """
    Provide a jitter to backoff.

    :param base:
    :return:
    """
    return base + random.random() * JITTER_S


def guest_get(url: str) -> requests.Response:
    """
    Guest get using the ao3 requester.

    :param url:
    :return:
    """
    time.sleep(jitter(GUEST_DELAY_S))
    return _req_guest.get(url, allow_redirects=True)


def load_work_guest(work_id: int) -> dict:
    """
    Load a work off the archive.

    :param work_id:
    :return:
    """
    sess = GuestAo3Session()
    w = Work(work_id, session=sess, load=True, load_chapters=False)
    return getattr(w, "metadata", {})
