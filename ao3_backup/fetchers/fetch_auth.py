from __future__ import annotations

import time

from typing import Tuple, Optional

from ao3.errors import RateLimitedException
from ao3_backup.utils import get_work_url
from ao3_backup.creds import CredentialManager
from ao3_backup.classify import classify_response
from ao3_backup.config import AUTH_DELAY_S
from ao3_backup.sessions import jitter
from ao3_backup.models import FetchResult

from ao3.works import Work


def fetch_with_auth(ao3_id: int, cred_manager: CredentialManager) -> FetchResult:
    """
    Attempt to fetch a work with authentication.

    :param ao3_id:
    :param cred_manager:
    :return:
    """

    url = get_work_url(ao3_id=ao3_id)
    rec = cred_manager.pick()

    if rec is None:
        return FetchResult(
            ao3_id=ao3_id,
            authed=True,
            outcome="error",
            status_code=0,
            html="",
            final_url=url,
            err="no-available-credentials",
            user=None,
            sess=None,
            meta=dict(),
        )

    sess = rec.ensure_session()

    try:
        time.sleep(jitter(AUTH_DELAY_S))
        resp = sess.session_requester.get(
            url, allow_redirects=True, force_session=sess.session
        )
        outcome = classify_response(url, resp.status_code, resp.text, resp.url)
        rec.mark_used()
        meta = {}

        if outcome in ("public", "restricted", "unrevealed"):

            try:
                w = Work(ao3_id, session=sess, load=True, load_chapters=False)
                meta = getattr(w, "metadata", {})
            except Exception:
                meta = {}

        return FetchResult(
            ao3_id=ao3_id,
            authed=True,
            outcome=outcome,
            status_code=resp.status_code,
            html=resp.text,
            final_url=resp.url,
            err=None,
            user=rec.username,
            sess=sess,
            meta=meta,
        )

    # Given how we've hardened the requester, this should be a rare error now
    except RateLimitedException as e:
        cred_manager.mark_rate_limited(rec.username)
        return FetchResult(
            ao3_id=ao3_id,
            authed=True,
            outcome="error",
            status_code=429,
            html="",
            final_url=url,
            err="rate-limited",
            user=rec.username,
            sess=None,
            meta={},
        )
