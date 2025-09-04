
"""
Contains dataclasses to better represent static objects off the archive.
"""


from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class HistoryItem:
    work_id: int
    work_title: str
    last_read_at: Optional[datetime]  # AO3 shows a date/time in the history row
    authors: list[str]                # display names (pseuds)
    chapter_count: Optional[int]      # if present in the row
    words: Optional[int]              # parsed from “Words: 12,345” if present
