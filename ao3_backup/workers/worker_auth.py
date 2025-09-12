
from __future__ import annotations

import concurrent.futures
import os
import time
import json
from sqlalchemy.orm import Session
from sqlalchemy import text

from ao3_backup.config import CLAIM_BATCH, PARALLELISM
from ao3_backup.db import get_engine, claim_batch, requeue, fetch_log
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

    def handle_one_safe(id_: int):
        """
        Attempt to deal with a single id which requires auth to work - safely.

        :param id_:
        :return:
        """
        try:
            return handle_one(id_)
        except Exception as e:
            with Session(eng) as s, s.begin():
                requeue(s, id_, delay_seconds=600, error_msg=str(e))
            return ("error", 0, str(e))

    def handle_one(id_: int):
        """
        Attempt to deal with a single id which requires auth to work - safely.

        :param id_:
        :return:
        """

        fetch_result = fetch_with_auth(
            id_, cred_man
        )

        outcome = fetch_result.outcome
        http = fetch_result.http_status_code
        html = fetch_result.html
        final_url = fetch_result.final_url
        err = fetch_result.err
        user = fetch_result.user
        sess = fetch_result.sess
        meta = fetch_result.meta

        if err:

            with Session(eng) as s, s.begin():
                requeue(s, id_, delay_seconds=900, error_msg=err)
                s.execute(
                    fetch_log.insert().values(
                        ao3_id=id_,
                        worker=name,
                        outcome="error",
                        http_status=http,
                        size_bytes=0,
                        credential=user,
                        error=err,
                    )
                )
            return ("error", http, err)

        if outcome in ("public", "restricted", "unrevealed"):
            size, sha = write_html_gz(id_, html)
            with Session(eng) as s, s.begin():
                s.execute(
                    text(
                        """
INSERT OR REPLACE INTO works (
    id,
    status,
    http_status,
    last_seen,
    last_fetched,
    content_sha256,
    size_bytes,
    title,
    words,
    chapters,
    language,
    rating,
    fandoms,
    relationships,
    characters,
    freeform_tags,
    kudos,
    bookmarks,
    hits,
    summary,
    raw_meta,
    restricted,
    needs_auth
)
VALUES (
    :id,
    :status,
    :http,
    datetime('now'),
    datetime('now'),
    :sha,
    :size,
    :title,
    :words,
    :chapters,
    :language,
    :rating,
    :fandoms,
    :relationships,
    :characters,
    :freeform,
    :kudos,
    :bookmarks,
    :hits,:summary,:raw_meta,:restricted,:needs_auth)
                """
                    ),
                    {
                        "id": id_,
                        "status": "public" if outcome == "public" else outcome,
                        "http": http,
                        "sha": sha,
                        "size": size,
                        "title": meta.get("title"),
                        "words": meta.get("words"),
                        "chapters": meta.get("chapters"),
                        "language": meta.get("language"),
                        "rating": meta.get("rating"),
                        "fandoms": (
                            json.dumps(meta.get("fandoms"))
                            if isinstance(meta.get("fandoms"), list)
                            else None
                        ),
                        "relationships": (
                            json.dumps(meta.get("relationships"))
                            if isinstance(meta.get("relationships"), list)
                            else None
                        ),
                        "characters": (
                            json.dumps(meta.get("characters"))
                            if isinstance(meta.get("characters"), list)
                            else None
                        ),
                        "freeform": (
                            json.dumps(meta.get("freeform") or meta.get("tags"))
                            if isinstance(
                                meta.get("freeform") or meta.get("tags"), list
                            )
                            else None
                        ),
                        "kudos": meta.get("kudos"),
                        "bookmarks": meta.get("bookmarks"),
                        "hits": meta.get("hits"),
                        "summary": meta.get("summary"),
                        "raw_meta": json.dumps(meta, ensure_ascii=False),
                        "restricted": 1 if outcome == "restricted" else 0,
                        "needs_auth": 1 if outcome == "restricted" else 0,
                    },
                )
                s.execute(text("DELETE FROM queue WHERE id = :id"), {"id": id_})
                s.execute(
                    fetch_log.insert().values(
                        ao3_id=id_,
                        worker=name,
                        outcome=outcome,
                        http_status=http,
                        size_bytes=size,
                        credential=user,
                    )
                )
            return (outcome, http, None)

        elif outcome == "not_found":
            with Session(eng) as s, s.begin():
                s.execute(
                    text(
                         """INSERT OR REPLACE INTO works 
                         (id,status,last_seen) 
                         VALUES (:id,'not_found',datetime('now'))"""
                    ),
                    {"id": id_},
                )
                s.execute(text("DELETE FROM queue WHERE id = :id"), {"id": id_})
                s.execute(
                    fetch_log.insert().values(
                        ao3_id=id_,
                        worker=name,
                        outcome="not_found",
                        http_status=http,
                        size_bytes=0,
                        credential=user,
                    )
                )
            return ("not_found", http, None)

        else:
            with Session(eng) as s, s.begin():
                requeue(
                    s, id_, delay_seconds=900, error_msg=f"unexpected outcome {outcome}"
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
