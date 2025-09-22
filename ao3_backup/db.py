"""
Models for interacting with the control database.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Tuple, Any

from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Boolean,
    DateTime,
    JSON,
    ForeignKey,
    Index,
    select,
    insert,
    update,
    delete,
    func,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import json

try:
    from .config import DB_URL
except Exception:
    DB_URL = "sqlite:///ao3_crawler.sqlite3"

metadata = MetaData()

# --------------------------- Tables ---------------------------

works = Table(
    "works",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("status", String(32), nullable=False),
    Column("http_status", Integer),
    Column(
        "last_seen", DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    ),
    Column("last_fetched", DateTime),
    Column("content_sha256", String(64)),
    Column("size_bytes", Integer),
    Column("title", Text),
    Column("words", Integer),
    Column("chapters", Integer),
    Column("language", String(64)),
    Column("rating", String(64)),
    Column("fandoms", JSON),
    Column("relationships", JSON),
    Column("characters", JSON),
    Column("freeform_tags", JSON),
    Column("kudos", Integer),
    Column("bookmarks", Integer),
    Column("hits", Integer),
    Column("summary", Text),
    Column("raw_meta", JSON),
    Column("error", Text),
    Column("restricted", Boolean, nullable=False, server_default=text("0")),
    Column("needs_auth", Boolean, nullable=False, server_default=text("0")),
)

queue = Table(
    "queue",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("mode", String(16), nullable=False, server_default=text("'guest'")),
    Column("priority", Integer, nullable=False, server_default=text("100")),
    Column(
        "next_attempt",
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("locked_by", String(64)),
    Column("locked_at", DateTime),
    Index("queue_mode_next_idx", "mode", "next_attempt", "priority", "id"),
    Index("queue_locked_idx", "locked_by", "locked_at"),
)

fetch_log = Table(
    "fetch_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ao3_id", BigInteger, nullable=False),
    Column("ts", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("worker", String(64), nullable=False),
    Column("outcome", String(32), nullable=False),
    Column("http_status", Integer),
    Column("size_bytes", Integer),
    Column("credential", String(128)),
    Column("error", Text),
    Index("fetch_log_id_ts", "id", "ts"),
)

authors = Table(
    "authors",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("slug", String(255), nullable=False, unique=True),
    Column("display_name", String(255)),
    Column("url", Text),
)

series = Table(
    "series",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("title", Text),
    Column("url", Text),
)

work_authors = Table(
    "work_authors",
    metadata,
    Column("work_id", BigInteger, ForeignKey("works.id"), nullable=False),
    Column("author_id", Integer, ForeignKey("authors.id"), nullable=False),
    Index("uq_work_authors", "work_id", "author_id", unique=True),
)

work_series = Table(
    "work_series",
    metadata,
    Column("work_id", BigInteger, ForeignKey("works.id"), nullable=False),
    Column("series_id", BigInteger, ForeignKey("series.id"), nullable=False),
    Column("position", Integer),
    Index("uq_work_series", "work_id", "series_id", unique=True),
)

blocks = Table(
    "blocks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("start", BigInteger, nullable=False),
    Column("stop", BigInteger, nullable=False),
    Column("mode", String(16), nullable=False, server_default=text("'guest'")),
    Column("priority", Integer, nullable=False, server_default=text("100")),
    Column(
        "created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    ),
    Column("started_at", DateTime),
    Column("finished_at", DateTime),
    Column("notes", Text),
    Index("blocks_range_idx", "start", "stop"),
)

# --------------------------- Engine / DDL ---------------------------


def get_engine(override_db_url: Optional[str] = None) -> Engine:
    """
    Return the Engine required to do database work.

    :return:
    """
    return create_engine(
        DB_URL if override_db_url is None else override_db_url,
        pool_pre_ping=True, future=True
    )


def create_all(override_db_url: Optional[str] = None) -> Engine:
    """
    Ensure the needed tables on the database.

    :return:
    """
    engine = get_engine(override_db_url=override_db_url)
    metadata.create_all(engine)
    return engine


# --------------------------- Helpers ---------------------------


def _dialect(db_session: Session) -> str:
    """
    Current SQL dialect of the operating DB session.

    :param db_session:
    :return:
    """
    return db_session.bind.dialect.name


def enqueue_range(
    db_session: Session, start: int, stop: int, mode: str = "guest", priority: int = 100
) -> int:
    """
    Enqueue a range of ids designated with a start and stop.

    :param db_session:
    :param start:
    :param stop:
    :param mode:
    :param priority:
    :return:
    """
    return enqueue_ids(db_session, range(start, stop + 1), mode=mode, priority=priority)


def enqueue_ids(
    db_session: Session, ids: Iterable[int], mode: str = "guest", priority: int = 100
) -> int:
    """
    Write a iterable of ids out to the queue for processing.

    :param db_session:
    :param ids:
    :param mode:
    :param priority:
    :return:
    """
    ids = [int(i) for i in ids]
    if not ids:
        return 0
    d = _dialect(db_session)
    if d == "sqlite":
        values = ",".join(f"({i}, '{mode}', {priority})" for i in ids)
        db_session.execute(
            text(f"INSERT OR IGNORE INTO queue (id, mode, priority) VALUES {values}")
        )

    elif d == "postgresql":

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = (
            pg_insert(queue)
            .values([{"id": i, "mode": mode, "priority": priority} for i in ids])
            .on_conflict_do_nothing(index_elements=["id"])
        )
        db_session.execute(stmt)

    else:
        for i in ids:
            try:
                db_session.execute(
                    insert(queue).values(id=i, mode=mode, priority=priority)
                )
            except Exception:
                pass

    return len(ids)


def claim_batch(
    db_session: Session, worker_id: str, batch_size: int, mode: str
) -> List[int]:
    """
    Put a claim in for a batch of ids to work on.

    :param db_session:
    :param worker_id:
    :param batch_size:
    :param mode:
    :return:
    """
    d = _dialect(db_session)

    if d == "postgresql":
        stmt = text(
            """
            UPDATE queue q
               SET locked_by = :worker, locked_at = NOW()
             WHERE q.id IN (
                SELECT id FROM queue
                 WHERE mode = :mode
                   AND locked_by IS NULL
                   AND next_attempt <= NOW()
                 ORDER BY priority ASC, id ASC
                 FOR UPDATE SKIP LOCKED
                 LIMIT :lim
             )
         RETURNING q.id
        """
        )
        res = db_session.execute(
            stmt, {"worker": worker_id, "mode": mode, "lim": batch_size}
        )
        return [r[0] for r in res.fetchall()]

    ids = [
        r.id
        for r in db_session.execute(
            select(queue.c.id)
            .where(queue.c.mode == mode)
            .where(queue.c.locked_by.is_(None))
            .where(queue.c.next_attempt <= func.current_timestamp())
            .order_by(queue.c.priority.asc(), queue.c.id.asc())
            .limit(batch_size)
        )
    ]
    if ids:
        db_session.execute(
            update(queue)
            .where(queue.c.id.in_(ids))
            .where(queue.c.locked_by.is_(None))
            .values(locked_by=worker_id, locked_at=func.current_timestamp())
        )
    return ids


def requeue(
    db_session: Session, ao3_id: int, delay_seconds: int, error_msg: Optional[str] = None
) -> None:
    """
    Requeue an id for later work.

    :param db_session:
    :param ao3_id:
    :param delay_seconds:
    :param error_msg:
    :return:
    """
    new_time = datetime.utcnow() + timedelta(seconds=int(delay_seconds))

    db_session.execute(
        update(queue)
        .where(queue.c.id == int(ao3_id))
        .values(
            attempts=queue.c.attempts + 1,
            locked_by=None,
            locked_at=None,
            next_attempt=new_time,
        )
    )

    if error_msg:
        db_session.execute(
            insert(fetch_log).values(
                ao3_id=int(ao3_id), worker="system", outcome="error", error=error_msg
            )
        )


def log_fetch(
    db_session: Session,
    ao3_id: int,
    worker: str,
    outcome: str,
    http_status: Optional[int] = None,
    size_bytes: Optional[int] = None,
    credential: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """
    Log an attempted fetch of a ao3 work.

    :param db_session:
    :param ao3_id:
    :param worker:
    :param outcome:
    :param http_status:
    :param size_bytes:
    :param credential:
    :param error:
    :return:
    """

    db_session.execute(
        insert(fetch_log).values(
            ao3_id=int(ao3_id),
            worker=worker,
            outcome=outcome,
            http_status=http_status,
            size_bytes=size_bytes,
            credential=credential,
            error=error,
        )
    )


def touch_work_status(session: Session, ao3_id: int, status: str) -> None:
    """
    Unix style touch of the work's status (creating if needed).

    :param session:
    :param ao3_id:
    :param status:
    :return:
    """
    rows = session.execute(
        update(works)
        .where(works.c.id == int(ao3_id))
        .values(status=status, last_seen=func.current_timestamp())
    ).rowcount

    if not rows:
        session.execute(
            insert(works).values(
                id=int(ao3_id), status=status, last_seen=datetime.utcnow()
            )
        )


# --------------- Blocks ---------------


def create_blocks_and_enqueue(
    db_session: Session,
    start: int,
    stop: int,
    block_size: int,
    mode: str = "guest",
    priority: int = 100,
) -> List[int]:
    """
    Create an entry in the blocks table for a block of ids and register them on the queue.

    :param db_session:
    :param start:
    :param stop:
    :param block_size:
    :param mode:
    :param priority:
    :return:
    """
    block_ids: List[int] = []
    cur = start
    while cur <= stop:
        b_start = cur
        b_stop = min(stop, cur + block_size - 1)

        res = db_session.execute(
            insert(blocks).values(
                start=b_start, stop=b_stop, mode=mode, priority=priority
            )
        )

        bid = res.inserted_primary_key[0]

        enqueue_range(db_session, b_start, b_stop, mode=mode, priority=priority)
        block_ids.append(int(bid))
        cur = b_stop + 1

    return block_ids


def block_progress(db_session: Session, block_id: int) -> dict:
    """
    Check for our progress through the block.

    :param db_session:
    :param block_id:
    :return:
    """
    b = db_session.execute(select(blocks).where(blocks.c.id == block_id)).first()
    if not b:
        return {"id": block_id, "error": "not found"}
    start, stop = int(b.start), int(b.stop)
    total = stop - start + 1
    remaining = (
        db_session.scalar(
            select(func.count())
            .select_from(queue)
            .where(queue.c.id.between(start, stop))
        )
        or 0
    )
    rows = db_session.execute(
        select(works.c.status, func.count())
        .where(works.c.id.between(start, stop))
        .group_by(works.c.status)
    ).all()
    status_counts = {r[0]: r[1] for r in rows}
    done = total - remaining
    return {
        "id": block_id,
        "range": [start, stop],
        "total": total,
        "remaining": remaining,
        "done": done,
        "statuses": status_counts,
    }

def declare_work_from_meta(db_session: Session,
                           ao3_id: int,
                           outcome: str,
                           http_status_code: int,
                           sha: str,
                           size: int,
                           meta: dict[str, Any]):
    """
    Read metadata from a meta dict and write it out to the works table.
    
    :param db_session: 
    :param ao3_id: 
    :param outcome: 
    :param http_status_code: 
    :param sha: 
    :param size: 
    :param meta: 
    :return: 
    """
    db_session.execute(
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
            :restricted,
            :needs_auth
)
    """
        ),
        {
            "id": ao3_id,
            "status": "public" if outcome == "public" else outcome,
            "http": http_status_code,
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


def declare_work(
    db_session: Session,
    ao3_id: int,
    outcome: str,
    http_status_code: int,
    sha: str,
    size: int,
    title: str,
    words: int,
    chapters: int,
    language: str,
    rating: str,
    fandoms: Optional[tuple[str]],
    relationships: Optional[tuple[str]],
    characters: Optional[tuple[str]],
    freeform: Optional[tuple[str]],
    kudos: int,
    bookmarks: int,
    hits: int,
    summary: str,
    raw_meta: str,
    remove_from_queue: bool = True,
) -> None:
    """
    Use the db_session to write out an update or replace to the works table.

    :param db_session:
    :param ao3_id:
    :param outcome:
    :param http_status_code:
    :param sha:
    :param size:
    :param title:
    :param words:
    :param chapters:
    :param language:
    :param rating:
    :param fandoms:
    :param relationships:
    :param characters:
    :param freeform:
    :param kudos:
    :param bookmarks:
    :param hits:
    :param summary:
    :param raw_meta:
    :param remove_from_queue: Also remove the entry from the queue.
    :return:
    """
    db_session.execute(
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
            0
)
    """
        ),
        {
            "id": ao3_id,
            "status": outcome,
            "http": http_status_code,
            "sha": sha,
            "size": size,
            "title": title,
            "words": words,
            "chapters": chapters,
            "language": language,
            "rating": rating,
            "fandoms": fandoms,
            "relationships": relationships,
            "characters": characters,
            "freeform": freeform,
            "kudos": kudos,
            "bookmarks": bookmarks,
            "hits": hits,
            "summary": summary,
            "raw_meta": raw_meta,
        },
    )
    # No need to go back for the moment
    if remove_from_queue:
        dequeue_work(db_session=db_session, ao3_id=ao3_id)


def declare_works_cannot_access(
    db_session: Session,
    ao3_id: int,
    status: str,
    http_status_code: int,
    sha: str,
    size: int,
):
    """
    The work is registered as restricted - note that on the works table.

    :param db_session:
    :param ao3_id:
    :param status:
    :param http_status_code:
    :param sha:
    :param size:
    :return:
    """
    db_session.execute(
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
        1,
        1
)
    """
        ),
        {
            "id": ao3_id,
            "status": status,
            "http": http_status_code,
            "sha": sha,
            "size": size,
        },
    )


def declare_work_not_found(db_session: Session, ao3_id: int) -> None:
    """
    Declare that a work cannot be found on the archie by updating the work table.

    :param db_session:
    :param ao3_id:
    :return:
    """
    db_session.execute(
        text(
            """
INSERT OR REPLACE INTO works (
        id,
        status,
        last_seen
) VALUES (
        :id,
        'not_found',
        datetime('now')
)"""
        ),
        {"id": ao3_id},
    )
    # Todo: seperate method
    db_session.execute(text("DELETE FROM queue WHERE id = :id"), {"id": ao3_id})


def enqueue_work_for_auth_access(db_session: Session, ao3_id: int) -> None:
    """
    Write a queue entry for auth access.

    :param db_session:
    :param ao3_id:
    :return:
    """
    db_session.execute(
        text(
            """
UPDATE queue
SET mode='auth', priority=50, locked_by=NULL, locked_at=NULL, next_attempt=CURRENT_TIMESTAMP
WHERE id = :id AND mode='guest';
"""
        ),
        {"id": ao3_id},
    )


def dequeue_work(
    db_session: Session, ao3_id: int, mode: Optional[str] = "update"
) -> None:
    """
    Remove the work from the queue, with various restrictions.

    :param db_session:
    :param ao3_id:
    :param mode:
    :return:
    """
    if mode:
        db_session.execute(
            text("DELETE FROM queue WHERE id = :id AND mode = :mode"),
            {"id": ao3_id, "mode": mode},
        )
    else:
        db_session.execute(text("DELETE FROM queue WHERE id = :id"), {"id": ao3_id})


def log_fetch_result(
    db_session: Session,
    ao3_id: int,
    worker_name: str,
    outcome: str,
    http_status_code: int,
    size_bytes: int,
    credential: Optional[str] = None,
    error: Optional[str] = None
) -> None:
    """
    Decare and enter a result on the fetch log table.

    :param db_session:
    :param worker_name:
    :param outcome:
    :param http_status_code:
    :param size_bytes:
    :param credential:
    :param error:
    :return:
    """
    if credential is None and error is None:
        db_session.execute(
            fetch_log.insert().values(
                ao3_id=ao3_id,
                worker=worker_name,
                outcome=outcome,
                http_status=http_status_code,
                size_bytes=size_bytes,
            )
        )
        return

    if credential is not None and error is not None:
        db_session.execute(
            fetch_log.insert().values(
                ao3_id=ao3_id,
                worker=worker_name,
                outcome=outcome,
                http_status=http_status_code,
                size_bytes=size_bytes,
                credential=credential,
                error=error
            )
        )
        return

    if credential is not None and error is None:

        db_session.execute(
            fetch_log.insert().values(
                ao3_id=ao3_id,
                worker=worker_name,
                outcome=outcome,
                http_status=http_status_code,
                size_bytes=size_bytes,
                credential=credential
            )
        )
        return

