
"""
Contains the API for the account class - which
"""

from typing import Union, Optional

import datetime

from functools import cached_property

import ao3.threadable as threadable
from ao3.api.object_api import BaseObjectAPI
from ao3.api.comment_session_work_api import Ao3SessionAPI, WorkAPI

import abc


class AccountAPI(abc.ABC, BaseObjectAPI):
    """
    API for the account class - representing your account on AO3.
    """
    session: "Ao3SessionAPI"

    def __init__(self, session: "Ao3SessionAPI") -> None:
        """
        Attach a session to this Account.

        The session has to be authenticated to do anything useful.
        :param session:
        """
        self.session = session

    @abc.abstractmethod
    def clear_cache(self) -> None:
        """
        Clear the internal properties cache

        :return:
        """
        raise NotImplementedError("Not supported for this Session type.")

    @abc.abstractmethod
    def get_work_subscriptions(self, use_threading: bool = False) -> list["WorkAPI"]:
        """
        Get subscribed works. Loads them if they haven't been previously

        Returns:
            list: List of work subscriptions
        """
        raise NotImplementedError("Not supported for this session type.")

    @abc.abstractmethod
    def get_series_subscriptions(self, use_threading: bool = False) -> list["Series"]:
        """
        Get subscribed series. Loads them if they haven't been previously

        Returns:
            list: List of series subscriptions
        """
        raise NotImplementedError("Not supported for this session type.")

    @abc.abstractmethod
    def get_user_subscriptions(self, use_threading: bool = False) -> list["User"]:
        """
        Get subscribed users. Loads them if they haven't been previously

        Returns:
            list: List of users subscriptions
        """
        raise NotImplementedError("Not supported for this session type.")

    @abc.abstractmethod
    def get_subscriptions(
        self, use_threading: bool = False
    ) -> list[Union["User", "Series", WorkAPI]]:
        """
        Get user's subscriptions.

        Loads them if they haven't been previously

        Returns:
            list: List of subscriptions
        """
        raise NotImplementedError("Not supported for this session type.")

    @threadable.threadable
    def load_subscriptions_threaded(self) -> None:
        """
        Get subscribed works using threads.

        This function is threadable.
        """
        raise NotImplementedError("Not supported for this session type.")

    def get_history(
        self,
        hist_sleep: int = 3,
        start_page: int = 0,
        max_pages: Optional[int] = None,
        timeout_sleep: Optional[int] = 60,
    ) -> Optional[list[list[WorkAPI, int, datetime.datetime]]]:
        """
       Get history works.

       Loads them if they haven't been previously.

       Arguments:
         hist_sleep (int to sleep between requests)
         start_page (int for page to start on, zero-indexed)
         max_pages  (int for page to end on, zero-indexed)
         timeout_sleep (int, if set will attempt to recovery from http errors, likely timeouts, if set to None
         will just attempt to load)

        takes two arguments the first hist_sleep is an int and is a sleep to run between pages of history to load to
        avoid hitting the rate limiter, the second is an int of the maximum number of pages of history to load, by
        default this is None so loads them all.

       Returns:
           list: List of tuples (Work, number-of-visits, datetime-last-visited)
        """
        raise NotImplementedError("Not supported for this session type.")

    def get_bookmarks(self, use_threading: bool = False) -> list[WorkAPI]:
        """
        Get bookmarked works. Loads them if they haven't been previously

        Returns:
            list: List of works
        """
        raise NotImplementedError("Not supported for this session type.")

    @threadable.threadable
    def load_bookmarks_threaded(self) -> None:
        """
        Get bookmarked works using threads.

        This function is threadable.
        """
        raise NotImplementedError("Not supported for this session type.")

    @cached_property
    def bookmarks(self) -> int:
        """Get the number of your bookmarks.

        Must be logged in to use.

        Returns:
            int: Number of bookmarks
        """
        raise NotImplementedError("Not supported for this session type.")

    def get_statistics(self, year: Optional[int] = None) -> dict[str, int]:
        """
        Return the user's statistics for a given year.

        :param year:
        :return:
        """
        raise NotImplementedError("Not supported for this session type.")

    def get_marked_for_later(
        self, sleep: int = 1, timeout_sleep: int = 60
    ) -> list[WorkAPI]:
        """
        Gets every marked for later work

        Arguments:
            sleep (int): The time to wait between page requests
            timeout_sleep (int): The time to wait after the rate limit is hit

        Returns:
            works (list): All marked for later works
        """
        raise NotImplementedError("Not supported for this session type.")
