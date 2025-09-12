
"""
Main entry point for the program.
"""


from __future__ import annotations

import os
import click
import threading

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select

from tabulate import tabulate

from ao3_backup.db import (
    get_engine,
    create_all,
    enqueue_range,
    create_blocks_and_enqueue,
    block_progress,
    works,
)
from ao3_backup.workers import worker_guest, worker_auth, worker_update


@click.group()
def cli():
    "AO3 crawler v0.6 — -w in-app parallel workers + blocks"


@cli.command("initdb")
def initdb():
    """
    Create

    :return:
    """
    create_all()
    click.echo("DB initialized.")


@cli.command("enqueue-range")
@click.option("--start", type=int, required=True)
@click.option("--stop", type=int, required=True)
@click.option("--mode", type=click.Choice(["guest", "auth", "update"]), default="guest")
@click.option("--priority", type=int, default=100)
def enqueue_range_cmd(start: int, stop: int, mode: str, priority: int) -> None:
    """
    Write a range of ids out to the queue to be processed.

    :param start:
    :param stop:
    :param mode:
    :param priority:
    :return:
    """
    eng = get_engine()
    with Session(eng) as s, s.begin():
        n = enqueue_range(s, start, stop, mode=mode, priority=priority)
    click.echo(f"Enqueued {n} ids [{start}..{stop}] in mode={mode}")


@cli.command("enqueue-blocks")
@click.option("--start", type=int, required=True)
@click.option("--stop", type=int, required=True)
@click.option("--block-size", type=int, default=10000, show_default=True)
@click.option("--mode", type=click.Choice(["guest", "auth", "update"]), default="guest")
@click.option("--priority", type=int, default=100)
def enqueue_blocks_cmd(
    start: int, stop: int, block_size: int, mode: str, priority: int
) -> None:
    """
    Create and enqueue a set of blocks for later processing.

    :param start:
    :param stop:
    :param block_size:
    :param mode:
    :param priority:
    :return:
    """
    eng = get_engine()
    with Session(eng) as s, s.begin():
        bids = create_blocks_and_enqueue(
            s, start, stop, block_size, mode=mode, priority=priority
        )
    click.echo(
        f"Created {len(bids)} blocks and enqueued IDs. First 5 block IDs: {bids[:5]}"
    )


def _spawn_workers(n: int, target, role: str, parallel: int | None):
    threads = []
    for i in range(n):
        name = f"{os.uname().nodename}-{os.getpid()}-{role}-{i+1}"
        t = threading.Thread(
            target=target,
            kwargs={"worker_name": name, "parallelism": parallel},
            daemon=True,
        )
        t.start()
        threads.append(t)
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        click.echo("\nStopping workers...")
        # Threads are daemon; process will exit.


@cli.command("worker-guest")
@click.option(
    "-w",
    "--workers",
    type=int,
    default=1,
    show_default=True,
    help="Number of in-process worker loops",
)
@click.option(
    "-p",
    "--parallel",
    type=int,
    default=None,
    help="Per-batch thread pool size (defaults to config.PARALLELISM)",
)
def worker_guest_cmd(workers: int, parallel: int | None) -> None:
    """
    Launch workers to download works that only need a guest account to access.

    :param workers:
    :param parallel:
    :return:
    """
    _spawn_workers(workers, worker_guest.run, "guest", parallel)


@cli.command("worker-auth")
@click.option("-w", "--workers", type=int, default=1, show_default=True)
@click.option("-p", "--parallel", type=int, default=None)
def worker_auth_cmd(workers: int, parallel: int | None) -> None:
    """
    Launch workers to process works which require auth to access.

    :param workers:
    :param parallel:
    :return:
    """
    _spawn_workers(workers, worker_auth.run, "auth", parallel)


@cli.command("worker-update")
@click.option("-w", "--workers", type=int, default=1, show_default=True)
@click.option("-p", "--parallel", type=int, default=None)
def worker_update_cmd(workers: int, parallel: int | None) -> None:
    """
    Launch the update workers to check for updates.

    :param workers:
    :param parallel:
    :return:
    """
    _spawn_workers(workers, worker_update.run, "update", parallel)


@cli.command("enqueue-updates")
@click.option(
    "--max-age-days",
    type=int,
    default=7,
    show_default=True,
    help="Revisit works not fetched in this many days",
)
@click.option(
    "--status",
    multiple=True,
    type=click.Choice(["public", "restricted", "unrevealed", "not_found", "error"]),
    default=["public", "restricted", "unrevealed"],
    show_default=True,
)
@click.option("--limit", type=int, default=200000, show_default=True)
@click.option("--priority", type=int, default=80, show_default=True)
def enqueue_updates_cmd(
    max_age_days: int, status: tuple[str], limit: int, priority: int
) -> None:
    """
    Queue a set of checks for updates.

    :param max_age_days:
    :param status:
    :param limit:
    :param priority:
    :return:
    """
    eng = get_engine()
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    with Session(eng) as s, s.begin():
        q = (
            select(works.c.id)
            .where((works.c.last_fetched.is_(None)) | (works.c.last_fetched <= cutoff))
            .where(works.c.status.in_(list(status)))
            .order_by(works.c.id.asc())
            .limit(limit)
        )
        ids = [r[0] for r in s.execute(q).all()]
        from .db import enqueue_ids

        n = enqueue_ids(s, ids, mode="update", priority=priority)
    click.echo(f"Selected {len(ids)} works; enqueued {n} for update.")


@cli.command("status-blocks")
@click.argument("block_ids", nargs=-1, type=int)
def status_blocks(block_ids) -> None:
    """
    Print the status of the currently active blocks.

    :param block_ids:
    :return:
    """
    from .db import blocks

    eng = get_engine()
    rows = []
    with Session(eng) as s:
        if not block_ids:
            q = s.execute(
                select(blocks.c.id).order_by(blocks.c.id.asc()).limit(50)
            ).all()
            block_ids = [r[0] for r in q]
        for bid in block_ids:
            p = block_progress(s, bid)
            st = p.get("statuses", {})
            rows.append(
                [
                    p["id"],
                    f"{p['range'][0]}..{p['range'][1]}",
                    p["total"],
                    p["done"],
                    p["remaining"],
                    st.get("public", 0),
                    st.get("restricted", 0),
                    st.get("unrevealed", 0),
                    st.get("not_found", 0),
                    st.get("error", 0),
                ]
            )
    headers = [
        "block_id",
        "range",
        "total",
        "done",
        "remaining",
        "public",
        "restricted",
        "unrevealed",
        "not_found",
        "error",
    ]
    click.echo(tabulate(rows, headers=headers, tablefmt="github"))
