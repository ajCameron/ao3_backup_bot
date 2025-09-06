
"""
The Account class contains methods to interact with your account.

(Including methods for history, bookmarks, inbox, e.t.c).
"""

from typing import Union, Optional

import logging

import bs4
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
from ao3.utils import workid_from_url, ao3_parse_date, ao3_parse_int
from ao3.models import HistoryItem

from ao3.errors import HTTPException


class Account(AccountAPI):
    """
    Represents an authenticated user's account on Ao3.
    """

    _subscriptions_url: str
    session: "Ao3SessionAPI"

    _history: Optional[list[HistoryItem]]

    _logger: logging.Logger

    def __init__(self, session: "Ao3SessionAPI") -> None:
        """
        Startup the Account - attached to an authenticated session.

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

        self._logger = logging.getLogger(f"Account-{self.username}-{id(self)}")

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
        self._logger.info("Clearing cache.")
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

    def get_subscription_page_count(self) -> int:
        """
        Return the number of pages of subscription the user has.

        :return:
        """
        return self._subscription_pages

    @cached_property
    def _subscription_pages(self) -> int:
        """
        How many pages of subscriptions does the user have?

        :return:
        """
        url = self._subscriptions_url.format(self.username, 1)

        self._logger.info(f"_subscription_pages making a request - {url = }")
        soup = self.request(url)
        self._logger.info(f"_subscription_pages has soup - {soup.title.string = }")

        return self._find_page_count_helper(soup)

    @staticmethod
    def _find_page_count_helper(soup: bs4.BeautifulSoup) -> int:
        """
        Several ao3 pages use the same structure to record page count - search for it and return.

        :param soup:
        :return:
        """

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

        return self._find_page_count_helper(soup)

    # Todo: To try and untangle the absolute mess which is the import chains, these should probably not be on session?
    def get_history(
        self,
        hist_sleep: int = 3,
        start_page: int = 0,
        max_pages: Optional[int] = None,
        timeout_sleep: Optional[int] = 60,
        force_refresh: bool = False
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
         use_load_history_fallback (bool):

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
                    fallback_count = 0
                    fail_at_count = 1000000
                    while loaded is False:
                        try:
                            self._load_history(page=page + 1)

                            loaded = True

                        except HTTPException:

                            time.sleep(timeout_sleep)

                        fallback_count += 1
                        if fallback_count > fail_at_count:
                            self._logger.error(f"fallback_count tripped as {fallback_count = }")
                            break

                # Check for maximum history page load
                if max_pages is not None and page >= max_pages:
                    return self._history

                # Again attempt to avoid rate limiter, sleep for a few
                # seconds between page requests.
                if hist_sleep is not None and hist_sleep > 0:
                    time.sleep(hist_sleep)

        return self._history

    def get_history_page_url(self, page: int = 1) -> str:
        """
        Return the URL for a particular page of the history to view.

        :param page:
        :return:
        """
        url = self._history_url.format(self.username, page)
        return url

    def _load_history(self, page: int = 1, override_soup: Optional[bs4.BeautifulSoup] = None) -> list[HistoryItem]:
        """
        Fallback method to load a single page from history.

        :param page:
        :param override_soup: Allows parsing testing by looping in existing soup instace
        :return:
        """
        def _retry_test(target_soup: bs4.BeautifulSoup) -> Optional[bs4._typing._AtMostOneElement]:
            return target_soup.find("ol", {"class": "reading work index group"})

        if override_soup is None:
            url = self._history_url.format(self.username, page)
            soup = self.request(url, retry_test=_retry_test)
        else:
            soup = override_soup

        history = _retry_test(soup)

        this_page_history = []
        for item in history.find_all("li", {"role": "article"}):

            # Authors
            h = item.find("h4", class_=re.compile(r"\bheading\b"))
            authors = [a.get_text(strip=True) for a in
                       (h.find_all("a", attrs={"rel": "author"}) if h else [])
                       ]

            # Title
            h = item.find("h4", class_=re.compile(r"\bheading\b"))
            a_title = h.find("a", href=re.compile(r"/works/\d+")) if h else None
            title = a_title.get_text(strip=True) if a_title else ""

            # Work ID
            work_id = None
            if a_title and a_title.has_attr("href"):
                m = re.search(r"/works/(\d+)", a_title["href"])
                if m:
                    work_id = int(m.group(1))

            # Datetime (AO3 often has <p class="datetime">12 Jan 2023</p>)
            last_read_at = None
            p_dt = item.find("p", class_=re.compile(r"\bdatetime\b"))
            if p_dt:
                last_read_at = ao3_parse_date(p_dt.get_text(" ", strip=True))

            # Chapter count and word count in the blurb meta (<dd> or spans)
            chapter_count = None
            words = None
            dd_tags = item.find_all(["dd", "span"])
            for dd in dd_tags:
                label = dd.get("class") or []
                txt = dd.get_text(" ", strip=True)
                if any("chapters" in c for c in label):
                    chapter_count = ao3_parse_int(txt)
                elif "words" in txt.lower() or any("words" in c for c in label):
                    words = ao3_parse_int(txt)

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

            # Fail fast if we can't identify the work
            if title is not None and work_id is not None:

                hist_item = HistoryItem(
                    work_id=work_id,
                    work_title=title,
                    last_read_at=last_read_at,
                    authors=authors,
                    chapter_count=chapter_count,
                    words=words,
                    visited_date=visited_date,
                    visited_num=visited_num,

                )

                if hist_item not in self._history:
                    self._history.append(hist_item)

                this_page_history.append(hist_item)

        return this_page_history


    @cached_property
    def _bookmark_pages(self) -> int:
        """
        How many pages of bookmarks does the user have?

        :return:
        """
        url = self._bookmarks_url.format(self.username, 1)
        soup = self.request(url)

        return self._find_page_count_helper(soup)

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

        def _retry_test(target_soup: bs4.BeautifulSoup) -> Optional[bs4._typing._AtMostOneElement]:
            return target_soup.find("ol", {"class": "bookmark index group"})

        soup = self.request(url, retry_test=_retry_test)

        bookmarks = soup.find("ol", {"class": "bookmark index group"})

        for book_m in bookmarks.find_all(
            "li", {"class": ["bookmark", "index", "group"]}
        ):
            authors = []
            recommended = False
            workid = -1
            workname = ""
            if book_m.h4 is not None:
                for a in book_m.h4.find_all("a"):
                    if "rel" in a.attrs.keys():
                        if "author" in a["rel"]:
                            authors.append(User(str(a.string), load=False))
                    elif a.attrs["href"].startswith("/works"):
                        workname = str(a.string)
                        workid = workid_from_url(a["href"])

                # Get whether the bookmark is recommended
                for span in book_m.p.find_all("span"):
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

        def _retry_test(target_soup: bs4.BeautifulSoup) -> Optional[bs4._typing._AtMostOneElement]:
            return target_soup.find("div", {"class": "bookmarks-index dashboard filtered region"})

        soup = self.request(url, retry_test=_retry_test)
        div = _retry_test(soup)

        if div is None:
            raise HTTPException(f"Call to get bookmarks returned malformed {url = } - {soup.title.str = }.")

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

            fallback_count = 0
            fail_at_count = 1000000

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

            fallback_count += 1
            if fallback_count > fail_at_count:
                self._logger.error(f"While loop is failing at {fallback_count = } - this is frankly alarming.")

            time.sleep(sleep)
        return works
