
"""
The Account class contains methods to interact with your account.

(Including methods for history, bookmarks, inbox, e.t.c).
"""

from typing import Union, Optional

from bs4 import BeautifulSoup

import re
import datetime
import time
import requests

from functools import cached_property

import ao3.threadable as threadable
from ao3.api.account_api import AccountAPI
from ao3.api.comment_session_work_api import WorkAPI, Ao3SessionAPI
from ao3.users import User
from ao3.series import Series
from ao3.utils import workid_from_url

from ao3.errors import HTTPException


class Account(AccountAPI):
    """
    Represents an authenticated user's account on Ao3.
    """

    _subscriptions_url: str
    session: "Ao3SessionAPI"

    def __init__(self, session: "Ao3SessionAPI") -> None:
        """
        Starup the Account - attached to an authenticated session.

        :param session:
        :return:
        """
        super().__init__(session=session)

        self.username = session.username

        self._subscriptions_url = (
            "https://archiveofourown.org/users/{0}/subscriptions?page={1:d}"
        )
        self._bookmarks_url = (
            "https://archiveofourown.org/users/{0}/bookmarks?page={1:d}"
        )
        self._history_url = "https://archiveofourown.org/users/{0}/readings?page={1:d}"

        self._bookmarks = None
        self._subscriptions = None
        self._history = None

    @property
    def _session(self) -> Optional["Ao3SessionAPI"]:
        """
        Hack to present the same API as most other classes.

        :return:
        """
        if self.session.logged_in:
            return self.session
        else:
            return None

    def clear_cache(self) -> None:
        """
        Zero out stored values.

        :return:
        """
        for attr in self.__class__.__dict__:
            if isinstance(getattr(self.__class__, attr), cached_property):
                if attr in self.__dict__:
                    delattr(self, attr)
        self._bookmarks = None
        self._subscriptions = None

    def get_subscriptions_url(self, page: int = 1) -> str:
        """
        Return the subscription URL for the current user.

        :param page:
        :return:
        """
        url = self._subscriptions_url.format(self.username, page)
        return url

    @cached_property
    def _subscription_pages(self) -> int:
        """
        How many pages of subscriptions does the user have?

        :return:
        """
        url = self._subscriptions_url.format(self.username, 1)
        soup = self.request(url)
        pages = soup.find("ol", {"title": "pagination"})
        if pages is None:
            return 1
        n = 1
        for li in pages.findAll("li"):
            text = li.getText()
            if text.isdigit():
                n = int(text)
        return n

    def get_subscription_url(self, page: int) -> str:
        """
        Return the URL of an actual subscription page.

        :param page:
        :return:
        """
        url = self._subscriptions_url.format(self.username, page)
        return url

    def get_work_subscriptions(self, use_threading: bool = False) -> list[WorkAPI]:
        """
        Get subscribed works. Loads them if they haven't been previously

        Returns:
            list: List of work subscriptions
        """
        from ao3.works import Work

        subs = self.get_subscriptions(use_threading)
        return list(filter(lambda obj: isinstance(obj, Work), subs))

    def get_series_subscriptions(self, use_threading: bool = False) -> list["Series"]:
        """
        Get subscribed series. Loads them if they haven't been previously

        Returns:
            list: List of series subscriptions
        """

        subs = self.get_subscriptions(use_threading)
        return list(filter(lambda obj: isinstance(obj, Series), subs))

    def get_user_subscriptions(self, use_threading: bool = False) -> list["User"]:
        """
        Get subscribed users. Loads them if they haven't been previously

        Returns:
            list: List of users subscriptions
        """

        subs = self.get_subscriptions(use_threading)
        return list(filter(lambda obj: isinstance(obj, User), subs))

    def get_subscriptions(
        self, use_threading: bool = False
    ) -> list[Union["User", "Series", WorkAPI]]:
        """
        Get user's subscriptions.

        Loads them if they haven't been previously

        Returns:
            list: List of subscriptions
        """

        if self._subscriptions is None:
            if use_threading:
                self.load_subscriptions_threaded()
            else:
                self._subscriptions = []
                for page in range(self._subscription_pages):
                    self._load_subscriptions(page=page + 1)
        return self._subscriptions

    @threadable.threadable
    def load_subscriptions_threaded(self) -> None:
        """
        Get subscribed works using threads.

        This function is threadable.
        """

        threads = []
        self._subscriptions = []
        for page in range(self._subscription_pages):
            threads.append(self._load_subscriptions(page=page + 1, threaded=True))
        for thread in threads:
            thread.join()

    @threadable.threadable
    def _load_subscriptions(self, page: int = 1) -> None:
        """

        :param page:
        :return:
        """
        url = self._subscriptions_url.format(self.username, page)

        soup = self.request(url)
        assert soup is not None, f"Call to subscriptions url at {url = } failed!"

        subscriptions = soup.find("dl", {"class": "subscription index group"})
        assert subscriptions is not None, f"Call to subscriptions url at {url = } failed! title = {soup.title.str}"

        for sub in subscriptions.find_all("dt"):
            type_ = "work"
            user = None
            series = None
            workid = None
            workname = None
            authors = []
            for a in sub.find_all("a"):
                if "rel" in a.attrs.keys():
                    if "author" in a["rel"]:
                        authors.append(User(str(a.string), load=False))
                elif a["href"].startswith("/works"):
                    workname = str(a.string)
                    workid = workid_from_url(a["href"])
                elif a["href"].startswith("/users"):
                    type_ = "user"
                    user = User(str(a.string), load=False)
                else:
                    type_ = "series"
                    workname = str(a.string)
                    series = int(a["href"].split("/")[-1])
            if type_ == "work":

                from ao3.works import Work

                new = Work(workid, load=False)
                setattr(new, "title", workname)
                setattr(new, "authors", authors)
                self._subscriptions.append(new)

            elif type_ == "user":
                self._subscriptions.append(user)

            elif type_ == "series":
                new = Series(series, load=False)
                setattr(new, "name", workname)
                setattr(new, "authors", authors)
                self._subscriptions.append(new)

    @cached_property
    def _history_pages(self) -> int:
        """
        Get the number of pages in the history.

        :return:
        """
        url = self._history_url.format(self.username, 1)
        soup = self.request(url)
        pages = soup.find("ol", {"title": "pagination"})
        if pages is None:
            return 1
        n = 1
        for li in pages.findAll("li"):
            text = li.getText()
            if text.isdigit():
                n = int(text)
        return n

    # Todo: To try and untangle the absolute mess which is the import chains, these should probably not be on session?
    # Todo: New class AuthenticatedUser?
    def get_history(
        self,
        hist_sleep: int = 3,
        start_page: int = 0,
        max_pages: Optional[int] = None,
        timeout_sleep: Optional[int] = 60,
        force_refresh: bool = False,
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
         force_refresh (bool):

        takes two arguments the first hist_sleep is an int and is a sleep to run between pages of history to load to
        avoid hitting the rate limiter, the second is an int of the maximum number of pages of history to load, by
        default this is None so loads them all.

       Returns:
           list: List of tuples (Work, number-of-visits, datetime-last-visited)
        """

        if self._history is None:
            self._history = []
            for page in range(start_page, self._history_pages):
                # If we are attempting to recover from errors then
                # catch and loop, otherwise just call and go
                if timeout_sleep is None:
                    self._load_history(page=page + 1)

                else:
                    loaded = False

                    while loaded is False:
                        try:
                            self._load_history(page=page + 1)
                            # print(f"Read history page {page+1}")
                            loaded = True

                        except HTTPException:
                            # print(f"History being rate limited, sleeping for {timeout_sleep} seconds")
                            time.sleep(timeout_sleep)

                # Check for maximum history page load
                if max_pages is not None and page >= max_pages:
                    return self._history

                # Again attempt to avoid rate limiter, sleep for a few
                # seconds between page requests.
                if hist_sleep is not None and hist_sleep > 0:
                    time.sleep(hist_sleep)

        return self._history

    def _load_history(self, page: int = 1) -> None:
        """
        Load a single page from history.

        :param page:
        :return:
        """
        url = self._history_url.format(self.username, page)
        soup = self.request(url)
        history = soup.find("ol", {"class": "reading work index group"})
        for item in history.find_all("li", {"role": "article"}):
            # authors = []
            workname = None
            workid = None
            for a in item.h4.find_all("a"):
                if a.attrs["href"].startswith("/works"):
                    workname = str(a.string)
                    workid = workid_from_url(a["href"])

            visited_date = None
            visited_num = 1
            for viewed in item.find_all("h4", {"class": "viewed heading"}):
                data_string = str(viewed)
                date_str = re.search(
                    "<span>Last visited:</span> (\d{2} .+ \d{4})", data_string
                )
                if date_str is not None:
                    date_time_obj = datetime.datetime.strptime(
                        date_str.group(1), "%d %b %Y"
                    )
                    visited_date = date_time_obj

                visited_str = re.search("Visited (\d+) times", data_string)
                if visited_str is not None:
                    visited_num = int(visited_str.group(1))

            from ao3.works import Work

            if workname is not None and workid is not None:
                new = Work(workid, load=False)
                setattr(new, "title", workname)
                # setattr(new, "authors", authors)
                hist_item = [new, visited_num, visited_date]
                # print(hist_item)
                if new not in self._history:
                    self._history.append(hist_item)

    @cached_property
    def _bookmark_pages(self) -> int:
        """
        How many pages of bookmarks does the user have?

        :return:
        """
        url = self._bookmarks_url.format(self.username, 1)
        soup = self.request(url)
        pages = soup.find("ol", {"title": "pagination"})
        if pages is None:
            return 1
        n = 1
        for li in pages.findAll("li"):
            text = li.getText()
            if text.isdigit():
                n = int(text)
        return n

    def get_bookmarks(self, use_threading: bool = False) -> list[WorkAPI]:
        """
        Get bookmarked works. Loads them if they haven't been previously

        Returns:
            list: List of works
        """

        if self._bookmarks is None:

            if use_threading:
                self.load_bookmarks_threaded()
            else:
                self._bookmarks = []
                for page in range(self._bookmark_pages):
                    self._load_bookmarks(page=page + 1)

        assert isinstance(self._bookmarks, list), "Type hacking"
        return self._bookmarks

    @threadable.threadable
    def load_bookmarks_threaded(self) -> None:
        """
        Get bookmarked works using threads.

        This function is threadable.
        """

        threads = []
        self._bookmarks = []
        for page in range(self._bookmark_pages):
            threads.append(self._load_bookmarks(page=page + 1, threaded=True))
        for thread in threads:
            thread.join()

    @threadable.threadable
    def _load_bookmarks(self, page: int = 1) -> None:
        """
        Load bookmarks into internal cache.

        :param page:
        :return:
        """
        url = self._bookmarks_url.format(self.username, page)
        soup = self.request(url)
        bookmarks = soup.find("ol", {"class": "bookmark index group"})
        for bookm in bookmarks.find_all(
            "li", {"class": ["bookmark", "index", "group"]}
        ):
            authors = []
            recommended = False
            workid = -1
            workname = ""
            if bookm.h4 is not None:
                for a in bookm.h4.find_all("a"):
                    if "rel" in a.attrs.keys():
                        if "author" in a["rel"]:
                            authors.append(User(str(a.string), load=False))
                    elif a.attrs["href"].startswith("/works"):
                        workname = str(a.string)
                        workid = workid_from_url(a["href"])

                # Get whether the bookmark is recommended
                for span in bookm.p.find_all("span"):
                    if "title" in span.attrs.keys():
                        if span["title"] == "Rec":
                            recommended = True

                from ao3.works import Work

                if workid != -1:
                    new = Work(workid, load=False)
                    setattr(new, "title", workname)
                    setattr(new, "authors", authors)
                    setattr(new, "recommended", recommended)
                    if new not in self._bookmarks:
                        self._bookmarks.append(new)

    @cached_property
    def bookmarks(self) -> int:
        """Get the number of your bookmarks.

        Must be logged in to use.

        Returns:
            int: Number of bookmarks
        """

        url = self._bookmarks_url.format(self.username, 1)
        soup = self.request(url)
        div = soup.find("div", {"class": "bookmarks-index dashboard filtered region"})
        if div is None:
            raise HTTPException(f"Call to get bookmarks returned malformed {url = }.")

        h2 = div.h2.text.split()

        try:
            return int(h2[4].replace(",", ""))
        except IndexError as e:
            try:
                return int(h2[0].replace(",", ""))
            except IndexError:
                pass
            raise IndexError(f"{h2 = } malformed and fallback failed "
                             f"- \n{url = }\n{div = }") from e

    def get_statistics(self, year: Optional[int] = None) -> dict[str, int]:
        """
        Return the user's statistics for a given year.

        :param year: Which year to retrieve the stats for?
        :return:
        """
        year = "All+Years" if year is None else str(year)
        url = f"https://archiveofourown.org/users/{self.username}/stats?year={year}"
        soup = self.request(url)
        stats = {}
        dt = soup.find("dl", {"class": "statistics meta group"})
        if dt is not None:

            for field in dt.findAll("dt"):
                name = field.getText()[:-1].lower().replace(" ", "_")
                if (
                    field.next_sibling is not None
                    and field.next_sibling.next_sibling is not None
                ):
                    value = field.next_sibling.next_sibling.getText().replace(",", "")
                    if value.isdigit():
                        stats[name] = int(value)

        return stats

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
        from ao3.works import Work

        page_raw = (
            self.request(
                f"https://archiveofourown.org/users/{self.username}/readings?page=1&show=to-read"
            )
            .find("ol", {"class": "pagination actions"})
            .find_all("li")
        )
        max_page = int(page_raw[len(page_raw) - 2].text)
        works = []
        for page in range(max_page):
            grabbed = False
            while grabbed is False:
                try:
                    work_page = self.request(
                        f"https://archiveofourown.org/users/{self.username}/readings?page={page + 1}&show=to-read"
                    )
                    works_raw = work_page.find_all("li", {"role": "article"})
                    for work in works_raw:
                        try:
                            work_id = int(work.h4.a.get("href").split("/")[2])
                            works.append(Work(work_id, session=self.session, load=False))
                        except AttributeError:
                            pass
                    grabbed = True
                except HTTPException:
                    time.sleep(timeout_sleep)
            time.sleep(sleep)
        return works
