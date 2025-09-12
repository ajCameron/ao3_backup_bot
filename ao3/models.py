
"""
Contains dataclasses to better represent static objects off the archive.
"""

from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class HistoryItem:
    """
    Represents a work item in the user's history.
    """
    work_id: int
    work_title: str
    last_read_at: Optional[datetime] = None             # AO3 shows a date/time in the history row
    authors: Optional[list[str]] = None                 # display names (pseuds)
    chapter_count: Optional[int] = None                 # if present in the row
    words: Optional[int] = None                         # parsed from “Words: 12,345” if present

    visited_date: Optional[datetime] = None
    visited_num: Optional[int] = None


@dataclass(frozen=True)
class SubscriptionItem:
    """
    Base class for anything which the user is subscribed to.
    """
    id: int                       # work_id / series_id / user_id
    title: str                    # work/series title or user pseud

    href: str                     # canonical AO3 href for the item



# Todo: Factory class which just takes any way to designate a work and gets you the work
@dataclass(frozen=True, kw_only=True)
class WorkSubscriptionItem(SubscriptionItem):
    """
    Represents a work the user is subscribed to.
    """

    user: Optional[str] = None    # Any users associated with the work
    user_url: Optional[str] = None # User url - if any associated with this work
    user_pseud: Optional[str] = None

    authors: Optional[list[str]] = None            # for work/series subs (empty for user subs)

    @property
    def work_id(self) -> int:
        """
        Proxy for the id of the work.

        :return:
        """
        return self.id


@dataclass(frozen=True, kw_only=True)
class SeriesSubscriptionItem(SubscriptionItem):
    """
    Represents a series the user is subscribed to.
    """

    authors: Optional[list[str]] = None            # for work/series subs (empty for user subs)

    @property
    def series_id(self) -> int:
        """
        Proxy for the id of the series.

        :return:
        """
        return self.id


@dataclass(frozen=True, kw_only=True)
class UserSubscriptionItem(SubscriptionItem):
    """
    Represents a User the user is subscribed to.
    """
    user: Optional[str] = None    # Any users associated with the work
    user_url: Optional[str] = None # User url - if any associated with this work
    user_pseud: Optional[str] = None

    @property
    def user_id(self) -> int:
        """
        Proxy for the id of the user.

        :return:
        """
        return self.id
