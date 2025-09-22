"""
Worker which attempts to consume update actions off the queue - in the case where auth is not needed.
"""

# Todo: Handle case of works BEING MADE private

from __future__ import annotations

from typing import Optional

import concurrent.futures
import os
import time
import json
from sqlalchemy.orm import Session

from ao3_backup.config import CLAIM_BATCH, PARALLELISM
from ao3_backup.db import (
    get_engine,
    claim_batch,
    requeue,
    fetch_log,
    declare_work,
    enqueue_work_for_auth_access,
    declare_works_cannot_access,
    dequeue_work,
    declare_work_not_found,
    log_fetch_result,
)
from ao3_backup.fetchers.fetch_public import fetch_public
from ao3_backup.storage import write_html_gz


def run_update_guest(worker_name: str = None, parallelism: int | None = None) -> None:
    """
    Run the update worker.

    :param worker_name:
    :param parallelism:
    :return:
    """
    eng = get_engine()
    name = worker_name or f"{os.uname().nodename}-{os.getpid()}-update"

    def handle_one_safe(ao3_id: int) -> tuple[str, int, str]:
        """
        Handle an id - wrapped in an exception block to ensure it never errors.

        :param ao3_id:
        :return:
        """
        try:
            return handle_one(ao3_id)
        except Exception as e:
            with Session(eng) as s, s.begin():
                requeue(s, ao3_id, delay_seconds=300, error_msg=str(e))
            return "error", 0, str(e)

    def handle_one(ao3_id: int) -> tuple[str, int, Optional[str]]:
        """
        Handle a single id.

        :param ao3_id:
        :return:
        """

        fetch_result = fetch_public(ao3_id)

        outcome = fetch_result.outcome
        http_status_code = fetch_result.http_status_code
        html = fetch_result.html
        final_url = fetch_result.final_url
        meta = fetch_result.meta

        # We've found and updated the work - and without auth
        if outcome == "public":

            size, sha = write_html_gz(ao3_id, html)
            with Session(eng) as s, s.begin():

                # Note our great success
                declare_work(
                    db_session=s,
                    ao3_id=ao3_id,
                    outcome="public",
                    http_status_code=http_status_code,
                    sha=sha,
                    size=size,
                    title=meta.get("title"),
                    words=meta.get("words"),
                    chapters=meta.get("chapters"),
                    language=meta.get("language"),
                    rating=meta.get("rating"),
                    fandoms=(
                        json.dumps(meta.get("fandoms"))
                        if isinstance(meta.get("fandoms"), list)
                        else None
                    ),
                    relationships=(
                        json.dumps(meta.get("relationships"))
                        if isinstance(meta.get("relationships"), list)
                        else None
                    ),
                    characters=(
                        json.dumps(meta.get("characters"))
                        if isinstance(meta.get("characters"), list)
                        else None
                    ),
                    freeform=(
                        json.dumps(meta.get("freeform") or meta.get("tags"))
                        if isinstance(meta.get("freeform") or meta.get("tags"), list)
                        else None
                    ),
                    kudos=meta.get("kudos"),
                    bookmarks=meta.get("bookmarks"),
                    hits=meta.get("hits"),
                    summary=meta.get("summary"),
                    raw_meta=json.dumps(meta, ensure_ascii=False),
                )

                s.execute(
                    fetch_log.insert().values(
                        ao3_id=ao3_id,
                        worker=name,
                        outcome="public-update",
                        http_status=http_status_code,
                        size_bytes=size,
                    )
                )
            return ("public-update", http_status_code, None)

        # We cannot download without auth
        elif outcome == "restricted":

            # Todo: Want to save both the guest html and the main html
            size, sha = write_html_gz(ao3_id, html)

            with Session(eng) as s, s.begin():

                declare_works_cannot_access(
                    db_session=s,
                    ao3_id=ao3_id,
                    status="restrcted",
                    http_status_code=http_status_code,
                    sha=sha,
                    size=size,
                )

                # We need to come back with an authed session to update this work
                dequeue_work(db_session=s, ao3_id=ao3_id)
                enqueue_work_for_auth_access(db_session=s, ao3_id=ao3_id)

                log_fetch_result(
                    db_session=s,
                    ao3_id=ao3_id,
                    worker_name=name,
                    outcome="restricted-update",
                    http_status_code=http_status_code,
                    size_bytes=size,
                )

            return ("restricted-update", http_status_code, None)

        # Todo: Are some works unrevealed to guests but revealed to users?
        elif outcome == "unrevealed":

            size, sha = write_html_gz(ao3_id, html)
            with Session(eng) as s, s.begin():

                # We're probably not getting this work
                declare_works_cannot_access(
                    db_session=s,
                    ao3_id=ao3_id,
                    status="unrevealed",
                    http_status_code=http_status_code,
                    sha=sha,
                    size=size,
                )

                # We've "succeeded" - remove from queue
                dequeue_work(db_session=s, ao3_id=ao3_id)

                # Log the fetch result to the table
                log_fetch_result(
                    db_session=s,
                    ao3_id=ao3_id,
                    worker_name=name,
                    outcome=outcome,
                    http_status_code=http_status_code,
                    size_bytes=size,
                )

            return ("unrevealed-update", http_status_code, None)

        elif outcome == "not_found":

            with Session(eng) as s, s.begin():

                # We're probably not getting this work
                declare_work_not_found(db_session=s, ao3_id=ao3_id)

                # We've "succeeded" - remove from queue
                dequeue_work(db_session=s, ao3_id=ao3_id)

                log_fetch_result(
                    db_session=s,
                    ao3_id=ao3_id,
                    worker_name=name,
                    outcome="not_found-update",
                    http_status_code=http_status_code,
                    size_bytes=0,
                )

            return ("not_found-update", http_status_code, None)

        # Something has gone kinda weird - try and record it
        else:

            with Session(eng) as s, s.begin():
                requeue(
                    s,
                    ao3_id,
                    delay_seconds=600,
                    error_msg=f"unexpected outcome {outcome}",
                )
            return ("error", 0, f"unexpected outcome {outcome}")

    while True:

        with Session(eng) as s, s.begin():
            ids = claim_batch(s, name, CLAIM_BATCH, mode="update")

        if not ids:
            time.sleep(2.0)
            continue

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=(parallelism or PARALLELISM)
        ) as pool:
            for id_, res in zip(ids, pool.map(handle_one_safe, ids)):
                outcome, http, err = res
                print(
                    f"[update] {id_}: {outcome} (http={http})"
                    + (f" ERR={err}" if err else "")
                )
