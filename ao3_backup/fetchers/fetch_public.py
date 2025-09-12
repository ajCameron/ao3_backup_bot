"""
Attempt to fetch a - nominally - publicly available work.
"""

from __future__ import annotations

from typing import Tuple

from ao3_backup.sessions import guest_get, load_work_guest
from ao3_backup.classify import classify_response
from ao3_backup.utils import get_work_url
from ao3_backup.models import FetchResult


BASE = "https://archiveofourown.org/works/{id}?view_full_work=true"


def fetch_public(ao3_id: int) -> FetchResult:
    """
    Attempt to load a work off the archive.

    :param ao3_id:
    :return:
    """
    url = get_work_url(ao3_id=ao3_id)
    resp = guest_get(url)
    outcome = classify_response(url, resp.status_code, resp.text, resp.url)
    meta = {}
    if outcome == "public":
        try:
            meta = load_work_guest(ao3_id)
        except Exception:
            meta = {}
    return FetchResult(
        ao3_id=ao3_id,
        authed=False,
        outcome=outcome,
        status_code=resp.status_code,
        html=resp.text,
        final_url=resp.url,
        err=None,
        user=None,
        sess=None,
        meta=meta,
    )
