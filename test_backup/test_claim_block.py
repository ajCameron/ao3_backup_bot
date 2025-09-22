

"""
Tests the create blocks and enqueue function.
"""

# tests/test_smoke_blocks.py
import os
from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine
from sqlalchemy import select, func

from ao3_backup.db import claim_batch

from pathlib import Path

import tempfile


def _import_db():
    # Import after env is set so config reads the temp DB URL.

    from ao3_backup import db as m  # fallback if your package is named differently
    return m


def test_claim_batch(tmp_path, monkeypatch) -> None:
    """
    Retrieve the engine and test claiming a block of ids.

    :param tmp_path:
    :param monkeypatch:
    :return:
    """
    db_file = tmp_path / "smoke2.sqlite3"

    monkeypatch.setenv("AO3_CRAWLER_DB_URL", f"sqlite:///{db_file}")

    m = _import_db()
    eng = m.create_all(override_db_url=f"sqlite:///{db_file}")

    start, stop, block_size = 1, 55_000, 10_000  # 6 blocks; 55k queue rows expected

    with Session(eng) as s, s.begin():

        block_ids = m.create_blocks_and_enqueue(
            s, start, stop, block_size, mode="guest", priority=123
        )
        assert len(block_ids) == 6, f"expected 6 blocks, got {len(block_ids)}"

        # Counts
        qn = s.scalar(select(func.count()).select_from(m.queue)) or 0
        bn = s.scalar(select(func.count()).select_from(m.blocks)) or 0

        assert qn == 55_000, f"expected 55,000 queued IDs, got {qn}"

        assert bn == 6, f"expected 6 blocks, got {bn}"

        # Range sanity
        min_id, max_id = s.execute(
            select(func.min(m.queue.c.id), func.max(m.queue.c.id))
        ).one()
        assert min_id == start and max_id == stop

        # Mode/priority sanity
        modes = dict(s.execute(
            select(m.queue.c.mode, func.count()).group_by(m.queue.c.mode)
        ).all())

        assert modes.get("guest") == 55_000

        min_pri, max_pri = s.execute(
            select(func.min(m.queue.c.priority), func.max(m.queue.c.priority))
        ).one()
        assert (min_pri, max_pri) == (123, 123)

        # Nothing should be pre-locked
        locked = s.scalar(
            select(func.count()).select_from(m.queue).where(m.queue.c.locked_by.is_not(None))
        ) or 0
        assert locked == 0

        # We have queued some ids - now claim some
        assert claim_batch(db_session=s, worker_id="test", batch_size=50, mode="guest") == [i for i in range(1, 51)]



