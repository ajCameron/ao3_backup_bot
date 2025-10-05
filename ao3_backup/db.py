"""
Minimal Rich UI logger for sqlite-downloader

Goals:
- No stdlib logging dependency. We expose just what sqlite-downloader needs.
- A single event queue the UI consumes (log lines + stats).
- Per-thread last-line display at the top; run summary (progress bars, dead domains) below.
- Safe fallback when Rich is unavailable (plain printing, no flicker).

Public surface:
  - download_log: has .info(.), .warning(.), .error(.), .exception(.)
  - stats: has .checked(), .queued(), .downloaded(), .skipped(), .failed(),
           .dead_domain(domain), .add_expected(n), .set_expected(n)
  - start_ui(), stop_ui()  (auto-starts on import)

Thread-safety: everything goes through a threadsafe Queue.
"""

from __future__ import annotations

import sys
import time
import queue
import threading
from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any
from importlib.util import find_spec
from importlib import import_module
from collections import Counter

# ---------------- soft import (no nesting) ----------------

def soft_import(modname: str, attr: str | None = None, default=None):
    if find_spec(modname) is None:
        return default
    mod = import_module(modname)
    return getattr(mod, attr) if attr else mod

# Rich is optional
_RichLive   = soft_import("rich.live", "Live")
_RichTable  = soft_import("rich.table", "Table")
_RichPanel  = soft_import("rich.panel", "Panel")
_RichLayout = soft_import("rich.layout", "Layout")
_RichBox    = soft_import("rich", "box")
_RichText   = soft_import("rich.text", "Text")
_RGroup     = soft_import("rich.console", "Group")
_RProgress  = {
    "Progress":            soft_import("rich.progress", "Progress"),
    "BarColumn":           soft_import("rich.progress", "BarColumn"),
    "TextColumn":          soft_import("rich.progress", "TextColumn"),
    "MofNCompleteColumn":  soft_import("rich.progress", "MofNCompleteColumn"),
    "TimeElapsedColumn":   soft_import("rich.progress", "TimeElapsedColumn"),
    "TimeRemainingColumn": soft_import("rich.progress", "TimeRemainingColumn"),
    "SpinnerColumn":       soft_import("rich.progress", "SpinnerColumn"),
}

def _has_rich() -> bool:
    return all([
        _RichLive, _RichTable, _RichPanel, _RichLayout, _RichBox, _RichText, _RGroup,
        _RProgress["Progress"], _RProgress["BarColumn"], _RProgress["TextColumn"],
        _RProgress["MofNCompleteColumn"], _RProgress["TimeElapsedColumn"],
        _RProgress["TimeRemainingColumn"], _RProgress["SpinnerColumn"],
    ])

# ---------------- event model ----------------

Level = Literal["INFO", "WARNING", "ERROR"]

@dataclass
class LogEvent:
    kind: Literal["log"] = "log"
    thread: str = ""
    level: Level = "INFO"
    message: str = ""

StatKind = Literal["checked", "queued", "downloaded", "skipped", "failed", "dead_domain", "add_total", "set_total"]

@dataclass
class StatEvent:
    kind: Literal["stat"] = "stat"
    stat: StatKind = "checked"
    n: int = 1
    domain: Optional[str] = None

Event = LogEvent | StatEvent

# ---------------- queues & state ----------------

_EVENTS: "queue.Queue[Event]" = queue.Queue()
_STOP = threading.Event()

@dataclass
class Stats:
    checked: int = 0
    queued: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    total_expected: int = 0
    dead: Counter = field(default_factory=Counter)

    def apply(self, e: StatEvent):
        if e.stat == "dead_domain" and e.domain:
            self.dead[e.domain] += e.n
            return
        if e.stat == "add_total":
            self.total_expected = max(0, self.total_expected + max(0, int(e.n)))
            return
        if e.stat == "set_total":
            self.total_expected = max(0, int(e.n))
            return
        # counters
        if hasattr(self, e.stat):
            setattr(self, e.stat, getattr(self, e.stat) + e.n)

_STATS = Stats()
# per-thread last message
_THREAD_LAST: Dict[str, str] = {}

# ---------------- the "logger" that the app uses ----------------

class _SimpleLogger:
    """
    Exposes the small surface sqlite-downloader expects:
      .info(msg), .warning(msg), .error(msg), .exception(msg)
    """
    __slots__ = ("_name",)
    def __init__(self, name: str = "downloader"): self._name = name

    def _put(self, level: Level, msg: str):
        # include current thread name; downloader already prefixes in some places,
        # but we add it consistently from here.
        th = threading.current_thread().name
        _EVENTS.put_nowait(LogEvent(thread=th, level=level, message=msg))

    def info(self, msg: str, *_, **__):    self._put("INFO", msg)
    def warning(self, msg: str, *_, **__): self._put("WARNING", msg)
    def error(self, msg: str, *_, **__):   self._put("ERROR", msg)

    def exception(self, msg: str, *_, **__):
        # We don’t print the traceback (Rich panel is compact). You can append traceback text if you prefer.
        self._put("ERROR", f"{msg} (exception)")

download_log = _SimpleLogger("downloader")

# ---------------- stat shim (as requested) ----------------

class StatShim:
    """
    Public interface for recording downloader events.
    Wraps queue posting so callers never touch internals directly.
    """
    def checked(self, n: int = 1) -> None:
        _EVENTS.put_nowait(StatEvent(stat="checked", n=n))
    def queued(self, n: int = 1) -> None:
        _EVENTS.put_nowait(StatEvent(stat="queued", n=n))
    def downloaded(self, n: int = 1) -> None:
        _EVENTS.put_nowait(StatEvent(stat="downloaded", n=n))
    def skipped(self, n: int = 1) -> None:
        _EVENTS.put_nowait(StatEvent(stat="skipped", n=n))
    def failed(self, n: int = 1) -> None:
        _EVENTS.put_nowait(StatEvent(stat="failed", n=n))
    def dead_domain(self, domain: str, n: int = 1) -> None:
        _EVENTS.put_nowait(StatEvent(stat="dead_domain", n=n, domain=domain))
    def add_expected(self, n: int = 1) -> None:
        """Increase expected total by event (so remote producers can contribute)."""
        _EVENTS.put_nowait(StatEvent(stat="add_total", n=n))
    def set_expected(self, n: int) -> None:
        """Hard-set expected total immediately."""
        _EVENTS.put_nowait(StatEvent(stat="set_total", n=n))

stats = StatShim()

# ---------------- UI loop: Rich or fallback ----------------

def _ui_loop_rich():
    # build layout
    Live = _RichLive; Table = _RichTable; Panel = _RichPanel; Layout = _RichLayout
    Text = _RichText; box = _RichBox; Group = _RGroup
    Progress = _RProgress["Progress"]; BarColumn=_RProgress["BarColumn"]
    TextColumn=_RProgress["TextColumn"]; MofN=_RProgress["MofNCompleteColumn"]
    TimeElapsed=_RProgress["TimeElapsedColumn"]; TimeRemaining=_RProgress["TimeRemainingColumn"]
    Spinner=_RProgress["SpinnerColumn"]

    # progress
    progress = Progress(
        Spinner(),
        TextColumn("[bold]{task.fields[title]}"),
        BarColumn(bar_width=None),
        MofN(),
        TextColumn("•"),
        TimeElapsed(),
        TextColumn("ETA"),
        TimeRemaining(),
        expand=True,
    )
    tasks = {
        "overall":    progress.add_task("", total=0, title="Overall"),
        "checked":    progress.add_task("", total=0, title="Checked"),
        "downloaded": progress.add_task("", total=0, title="Downloaded"),
        "skipped":    progress.add_task("", total=0, title="Skipped"),
        "failed":     progress.add_task("", total=0, title="Failed"),
    }

    def render_threads():
        t = Table(title="Thread Status", box=box.SIMPLE_HEAVY)
        t.add_column("Thread", style="bold cyan", no_wrap=True)
        t.add_column("Last line", style="white", overflow="fold")
        for th in sorted(_THREAD_LAST):
            t.add_row(th, _THREAD_LAST[th][:1000])
        return t

    def render_summary():
        # set totals
        te = max(0, int(_STATS.total_expected))
        done = _STATS.downloaded + _STATS.skipped + _STATS.failed
        for key in tasks:
            progress.update(tasks[key], total=te)
        progress.update(tasks["overall"], completed=min(done, te))
        progress.update(tasks["checked"], completed=min(_STATS.checked, te))
        progress.update(tasks["downloaded"], completed=min(_STATS.downloaded, te))
        progress.update(tasks["skipped"], completed=min(_STATS.skipped, te))
        progress.update(tasks["failed"], completed=min(_STATS.failed, te))

        # dead domains small table (if any)
        if _STATS.dead:
            dd = Table.grid(expand=True)
            dd.add_column(justify="left"); dd.add_column(justify="right")
            dd.add_row(Text("Dead domains (top)", style="bold"), "")
            for d, c in _STATS.dead.most_common(7):
                dd.add_row(d, str(c))
            body = Group(progress, dd)
        else:
            body = progress
        return Panel(body, title="Run Summary", border_style="cyan", padding=(0,1))

    layout = Layout(name="root")
    layout.split_column(
        Layout(name="top", ratio=4),
        Layout(name="bottom", size=10),
    )
    layout["top"].update(render_threads())
    layout["bottom"].update(render_summary())

    live = Live(layout, refresh_per_second=10, screen=True, auto_refresh=False)
    live.__enter__()
    try:
        while not _STOP.is_set():
            # drain a bunch of events quickly
            drained = 0
            while drained < 300:
                try:
                    ev = _EVENTS.get_nowait()
                except queue.Empty:
                    break
                drained += 1
                if isinstance(ev, LogEvent):
                    _THREAD_LAST[ev.thread] = f"[{ev.level}] {ev.message}"
                else:
                    _STATS.apply(ev)

            # render
            layout["top"].update(render_threads())
            layout["bottom"].update(render_summary())
            live.update(layout, refresh=True)

            # gentle idle
            time.sleep(0.05)
    finally:
        live.__exit__(None, None, None)

def _ui_loop_fallback():
    """
    Minimal fallback: print log lines and a throttled summary line.
    No flicker; still consumes events to keep counts correct.
    """
    last_summary = 0.0
    while not _STOP.is_set():
        try:
            ev = _EVENTS.get(timeout=0.1)
        except queue.Empty:
            pass
        else:
            if isinstance(ev, LogEvent):
                # single-line compact print
                sys.stdout.write(f"[{ev.thread}] {ev.level}: {ev.message}\n")
                sys.stdout.flush()
            else:
                _STATS.apply(ev)

        now = time.time()
        if now - last_summary > 1.0:
            te = _STATS.total_expected
            done = _STATS.downloaded + _STATS.skipped + _STATS.failed
            sys.stdout.write(
                f"[Summary] checked={_STATS.checked} "
                f"downloaded={_STATS.downloaded} skipped={_STATS.skipped} failed={_STATS.failed} "
                f"done/total={done}/{te}\n"
            )
            if _STATS.dead:
                top = ", ".join(f"{d}:{c}" for d,c in _STATS.dead.most_common(3))
                sys.stdout.write(f"[Dead domains] {top}\n")
            sys.stdout.flush()
            last_summary = now

        # avoid tight loop
        time.sleep(0.02)

# ---------------- lifecycle ----------------

_UI_THREAD: Optional[threading.Thread] = None

def start_ui():
    global _UI_THREAD
    if _UI_THREAD and _UI_THREAD.is_alive():
        return
    _STOP.clear()
    target = _ui_loop_rich if _has_rich() else _ui_loop_fallback
    _UI_THREAD = threading.Thread(target=target, name="ui", daemon=True)
    _UI_THREAD.start()

def stop_ui():
    _STOP.set()
    if _UI_THREAD:
        _UI_THREAD.join(timeout=2.0)

# ---------------- auto-start ----------------

start_ui()
