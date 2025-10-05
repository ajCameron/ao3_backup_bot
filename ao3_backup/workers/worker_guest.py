"""
Worker which downloads guest accessible works from the archive.
"""

from __future__ import annotations

import concurrent.futures
import os
import time
import json
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ao3_backup.config import CLAIM_BATCH, PARALLELISM
from ao3_backup.db import (
    get_engine,
    claim_batch,
    requeue,
    fetch_log,
    declare_work,
    declare_works_cannot_access,
    declare_work_not_found,
    enqueue_work_for_auth_access,
    dequeue_work,
    log_fetch_result,
)
from ao3_backup.fetchers.fetch_public import fetch_public
from ao3_backup.storage import write_html_gz


def run(worker_name: str = None, parallelism: int | None = None) -> None:
    """
    Run the worker - consume ids and try and access them in guest mode.

    :param worker_name:
    :param parallelism:
    :return:
    """
    eng = get_engine()
    name = worker_name or f"{os.uname().nodename}-{os.getpid()}-guest"

    def handle_one_safe(ao3_id: int) -> tuple[str, int, str]:
        """
        Attempt to process a single id - safely.

        :param ao3_id:
        :return:
        """
        try:
            return handle_one_guest(ao3_id=ao3_id, eng=eng, name=name)
        except Exception as e:
            with Session(eng) as s, s.begin():
                requeue(s, ao3_id, delay_seconds=300, error_msg=str(e))
            return ("error", 0, str(e))

    while True:

        with Session(eng) as s, s.begin():
            ids = claim_batch(s, name, CLAIM_BATCH, mode="guest")

        if not ids:
            time.sleep(2.0)
            continue

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=(parallelism or PARALLELISM)
        ) as pool:
            for id_, res in zip(ids, pool.map(handle_one_safe, ids)):
                outcome, http, err = res
                print(
                    f"[guest] {id_}: {outcome} (http={http})"
                    + (f" ERR={err}" if err else "")
                )


def handle_one_guest(ao3_id: int, eng: Engine, name: str) -> tuple[str, int, str]:
    """
    Attempt to handle a single id - dangerously.

    :param ao3_id:
    :return:
    """
    # todo: all fetch publics need to be fixed
    outcome, http, html, final_url, meta = fetch_public(ao3_id)

    # The work is public and has been downloaded
    if outcome == "public":

        size, sha = write_html_gz(ao3_id, html)

        with Session(eng) as s, s.begin():

            declare_work(
                db_session=s,
                ao3_id=ao3_id,
                outcome="public",
                http_status_code=http,
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
                remove_from_queue=True,
            )

            log_fetch_result(
                db_session=s,
                ao3_id=ao3_id,
                worker_name=name,
                outcome="public",
                http_status_code=http,
                size_bytes=size,
            )

        return (outcome, http, None)

    elif outcome == "restricted":

        size, sha = write_html_gz(ao3_id, html)
        with Session(eng) as s, s.begin():

            declare_works_cannot_access(
                db_session=s,
                ao3_id=ao3_id,
                status='restricted',
                http_status_code=http,
                sha=sha,
                size=size
            )

            enqueue_work_for_auth_access(db_session=s, ao3_id=ao3_id)

            # Should already be gone - but to make sure
            dequeue_work(db_session=s, ao3_id=ao3_id, mode="guest")

            s.execute(
                fetch_log.insert().values(
                    ao3_id=ao3_id,
                    worker=name,
                    outcome="restricted",
                    http_status=http,
                    size_bytes=size,
                )
            )
        return ("restricted", http, None)

    elif outcome == "unrevealed":

        size, sha = write_html_gz(ao3_id, html)
        with Session(eng) as s, s.begin():

            declare_works_cannot_access(
                db_session=s,
                ao3_id=ao3_id,
                status='unrevealed',
                http_status_code=http,
                sha=sha,
                size=size
            )

            dequeue_work(db_session=s, ao3_id=ao3_id)

            log_fetch_result(
                db_session=s,
                ao3_id=ao3_id,
                worker_name=name,
                outcome="unrevealed",
                http_status_code=http,
                size_bytes=size
            )

        return ("unrevealed", http, None)

    elif outcome == "not_found":

        with Session(eng) as s, s.begin():

            declare_work_not_found(db_session=s, ao3_id=ao3_id)

            log_fetch_result(
                db_session=s,
                ao3_id=ao3_id,
                worker_name=name,
                outcome=outcome,
                http_status_code=http,
                size_bytes=0
            )

        return ("not_found", http, None)

    else:

        with Session(eng) as s, s.begin():
            requeue(
                s,
                ao3_id,
                delay_seconds=600,
                error_msg=f"unexpected outcome {outcome}",
            )

        return ("error", 0, f"unexpected outcome {outcome}")
