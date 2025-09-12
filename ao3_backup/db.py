
"""
Models for interacting with the control database.
"""


from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Tuple

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


def get_engine() -> Engine:
    """
    Return the Engine required to do database work.

    :return:
    """
    return create_engine(DB_URL, pool_pre_ping=True, future=True)


def create_all() -> None:
    """
    Ensure the needed tables on the database.

    :return:
    """
    engine = get_engine()
    metadata.create_all(engine)


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
    db_session: Session, id_: int, delay_seconds: int, error_msg: Optional[str] = None
) -> None:
    """
    Requeue an id for later work.

    :param db_session:
    :param id_:
    :param delay_seconds:
    :param error_msg:
    :return:
    """
    new_time = datetime.utcnow() + timedelta(seconds=int(delay_seconds))

    db_session.execute(
        update(queue)
        .where(queue.c.id == int(id_))
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
                ao3_id=int(id_), worker="system", outcome="error", error=error_msg
            )
        )


def complete(db_session: Session, ao3_id: int) -> None:
    """
    Mark a ao3 id as completed.

    :param db_session:
    :param ao3_id:
    :return:
    """
    db_session.execute(delete(queue).where(queue.c.id == int(ao3_id)))


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


def touch_work_status(session: Session, *, id_: int, status: str) -> None:
    """
    Unix style touch of the work's status (creating if needed).

    :param session:
    :param id_:
    :param status:
    :return:
    """
    rows = session.execute(
        update(works)
        .where(works.c.id == int(id_))
        .values(status=status, last_seen=func.current_timestamp())
    ).rowcount

    if not rows:
        session.execute(
            insert(works).values(
                id=int(id_), status=status, last_seen=datetime.utcnow()
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
