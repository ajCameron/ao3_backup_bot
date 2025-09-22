from __future__ import annotations

import concurrent.futures
import os
import time
import json
from sqlalchemy.orm import Session
from sqlalchemy import text

from ao3_backup.config import CLAIM_BATCH, PARALLELISM
from ao3_backup.db import get_engine, claim_batch, requeue, fetch_log, declare_work_from_meta, dequeue_work, log_fetch_result, declare_work_not_found
from ao3_backup.fetchers.fetch_auth import fetch_with_auth
from ao3_backup.storage import write_html_gz
from ao3_backup.creds import CredentialManager


def run(worker_name: str = None, parallelism: int | None = None):
    """
    Gets and then tries to handle story ids which have been determined to require auth to access.

    :param worker_name: Name to assign
    :param parallelism:
    :return:
    """
    eng = get_engine()
    cred_man = CredentialManager()
    name = worker_name or f"{os.uname().nodename}-{os.getpid()}-auth"

    def handle_one_safe(ao3_id: int) -> tuple[str, int, str]:
        """
        Attempt to deal with a single id which requires auth to work - safely.

        :param ao3_id:
        :return:
        """
        try:
            return handle_one(ao3_id)
        except Exception as e:
            with Session(eng) as s, s.begin():
                requeue(s, ao3_id, delay_seconds=600, error_msg=str(e))
            return ("error", 0, str(e))

    def handle_one(ao3_id: int):
        """
        Attempt to deal with a single id which requires auth to work - safely.

        :param ao3_id:
        :return:
        """

        fetch_result = fetch_with_auth(ao3_id, cred_man)

        outcome = fetch_result.outcome
        http = fetch_result.http_status_code
        html = fetch_result.html
        final_url = fetch_result.final_url
        err = fetch_result.err
        user = fetch_result.user
        meta = fetch_result.meta

        # Something has gone badly wrong - reqeue
        if err:

            with Session(eng) as s, s.begin():

                requeue(s, ao3_id, delay_seconds=900, error_msg=err)

                log_fetch_result(
                    db_session=s,
                    ao3_id=ao3_id,
                    worker_name=name,
                    outcome="error",
                    http_status_code=http,
                    size_bytes=0,
                    credential=user,
                    error=err
                )

            return ("error", http, err)

        if outcome in ("public", "restricted", "unrevealed"):

            # Write the result of the fetch out
            size, sha = write_html_gz(ao3_id, html)

            with Session(eng) as s, s.begin():

                declare_work_from_meta(
                    db_session=s,
                    ao3_id=ao3_id,
                    outcome=outcome,
                    http_status_code=http,
                    sha=sha,
                    size=size,
                    meta=meta
                )

                # However it's gone, we've done our best
                dequeue_work(db_session=s, ao3_id=ao3_id)

                log_fetch_result(
                    db_session=s,
                    ao3_id=ao3_id,
                    worker_name=name,
                    outcome=outcome,
                    http_status_code=http,
                    size_bytes=size,
                    credential=user
                )

            return (outcome, http, None)

        # We can't find the work, and am probably not going to
        elif outcome == "not_found":
            with Session(eng) as s, s.begin():

                declare_work_not_found(db_session=s, ao3_id=ao3_id)

                dequeue_work(db_session=s, ao3_id=ao3_id)

                log_fetch_result(
                    db_session=s,
                    ao3_id=ao3_id,
                    worker_name=name,
                    outcome="not_found",
                    http_status_code=http,
                    size_bytes=0,
                    credential=user
                )

            return ("not_found", http, None)

        else:

            with Session(eng) as s, s.begin():

                requeue(
                    db_session=s,
                    ao3_id=ao3_id,
                    delay_seconds=900,
                    error_msg=f"unexpected outcome {outcome}",
                )

                log_fetch_result(
                    db_session=s,
                    ao3_id=ao3_id,
                    worker_name=name,
                    outcome="unexpected",
                    http_status_code=http,
                    size_bytes=0,
                    credential=user
                )

            return ("error", 0, f"unexpected outcome {outcome}")

    while True:
        with Session(eng) as s, s.begin():
            ids = claim_batch(s, name, CLAIM_BATCH, mode="auth")

        if not ids:
            time.sleep(2.0)
            continue

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=(parallelism or PARALLELISM)
        ) as pool:

            for id_, res in zip(ids, pool.map(handle_one_safe, ids)):
                outcome, http, err = res
                print(
                    f"[auth] {id_}: {outcome} (http={http})"
                    + (f" ERR={err}" if err else "")
                )
