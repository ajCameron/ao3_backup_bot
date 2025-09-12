
"""
Worker which checks for updates to the given ids.
"""


from __future__ import annotations

import concurrent.futures
import os
import time
import json
from sqlalchemy.orm import Session
from sqlalchemy import text

from config import CLAIM_BATCH, PARALLELISM
from db import get_engine, claim_batch, requeue, fetch_log
from fetchers.fetch_public import fetch_public
from storage import write_html_gz


def run(worker_name: str = None, parallelism: int | None = None):
    eng = get_engine()
    name = worker_name or f"{os.uname().nodename}-{os.getpid()}-update"

    def handle_one(id_: int):
        try:
            outcome, http, html, final_url, meta = fetch_public(id_)
            if outcome == "public":
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
        :hits,
        :summary,
        :raw_meta,
        0,
        0)
                    """
                        ),
                        {
                            "id": id_,
                            "status": "public",
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
                        },
                    )
                    s.execute(text("DELETE FROM queue WHERE id = :id"), {"id": id_})
                    s.execute(
                        fetch_log.insert().values(
                            ao3_id=id_,
                            worker=name,
                            outcome="public-update",
                            http_status=http,
                            size_bytes=size,
                        )
                    )
                return ("public-update", http, None)
            elif outcome == "restricted":
                size, sha = write_html_gz(id_, html)
                with Session(eng) as s, s.begin():
                    s.execute(
                        text(
                            """
                        INSERT OR REPLACE INTO works (id,status,http_status,last_seen,last_fetched,content_sha256,size_bytes,restricted,needs_auth)
                        VALUES (:id,'restricted',:http,datetime('now'),datetime('now'),:sha,:size,1,1)
                    """
                        ),
                        {"id": id_, "http": http, "sha": sha, "size": size},
                    )
                    s.execute(
                        text(
                            """INSERT OR IGNORE INTO queue (id, mode, priority) VALUES (:id, 'auth', 50)"""
                        ),
                        {"id": id_},
                    )
                    s.execute(
                        text("DELETE FROM queue WHERE id = :id AND mode='update'"),
                        {"id": id_},
                    )
                    s.execute(
                        fetch_log.insert().values(
                            ao3_id=id_,
                            worker=name,
                            outcome="restricted-update",
                            http_status=http,
                            size_bytes=size,
                        )
                    )
                return ("restricted-update", http, None)
            elif outcome == "unrevealed":
                size, sha = write_html_gz(id_, html)
                with Session(eng) as s, s.begin():
                    s.execute(
                        text(
                            """
                        INSERT OR REPLACE INTO works (id,status,http_status,last_seen,last_fetched,content_sha256,size_bytes)
                        VALUES (:id,'unrevealed',:http,datetime('now'),datetime('now'),:sha,:size)
                    """
                        ),
                        {"id": id_, "http": http, "sha": sha, "size": size},
                    )
                    s.execute(text("DELETE FROM queue WHERE id = :id"), {"id": id_})
                    s.execute(
                        fetch_log.insert().values(
                            ao3_id=id_,
                            worker=name,
                            outcome="unrevealed-update",
                            http_status=http,
                            size_bytes=size,
                        )
                    )
                return ("unrevealed-update", http, None)
            elif outcome == "not_found":
                with Session(eng) as s, s.begin():
                    s.execute(
                        text(
                            """INSERT OR REPLACE INTO works (id,status,last_seen) VALUES (:id,'not_found',datetime('now'))"""
                        ),
                        {"id": id_},
                    )
                    s.execute(text("DELETE FROM queue WHERE id = :id"), {"id": id_})
                    s.execute(
                        fetch_log.insert().values(
                            ao3_id=id_,
                            worker=name,
                            outcome="not_found-update",
                            http_status=http,
                            size_bytes=0,
                        )
                    )
                return ("not_found-update", http, None)
            else:
                with Session(eng) as s, s.begin():
                    requeue(
                        s,
                        id_,
                        delay_seconds=600,
                        error_msg=f"unexpected outcome {outcome}",
                    )
                return ("error", 0, f"unexpected outcome {outcome}")
        except Exception as e:
            with Session(eng) as s, s.begin():
                requeue(s, id_, delay_seconds=300, error_msg=str(e))
            return ("error", 0, str(e))


    while True:
        with Session(eng) as s, s.begin():
            ids = claim_batch(s, name, CLAIM_BATCH, mode="update")
        if not ids:
            time.sleep(2.0)
            continue
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=(parallelism or PARALLELISM)
        ) as pool:
            for id_, res in zip(ids, pool.map(handle_one, ids)):
                outcome, http, err = res
                print(
                    f"[update] {id_}: {outcome} (http={http})"
                    + (f" ERR={err}" if err else "")
                )
