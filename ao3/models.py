
"""
Contains dataclasses to better represent static objects off the archive.
"""


from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class HistoryItem:
    """
    Represents an item in the users history.
    """
    work_id: int
    work_title: str
    last_read_at: Optional[datetime] = None             # AO3 shows a date/time in the history row
    authors: Optional[list[str]] = None                 # display names (pseuds)
    chapter_count: Optional[int] = None                 # if present in the row
    words: Optional[int]  =None                         # parsed from “Words: 12,345” if present

    visited_date: Optional[datetime] = None
    visited_num: Optional[int] = None

