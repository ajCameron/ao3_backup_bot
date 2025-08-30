import datetime
import re
import time
from functools import cached_property

from typing import Optional, Union


import requests
from bs4 import BeautifulSoup

from ao3.errors import UnexpectedResponseException, RateLimitedException, LoginException, HTTPException
from ao3 import threadable, utils
from ao3.series import Series
from ao3.users import User
from ao3.api.comment_session_work_api import Ao3SessionAPI, WorkAPI

# ao3/session.py (only the login bits shown/changed)
from ao3.session.session_pool import session_pool
from ao3.requester import requester, Requester
from ao3.errors import LoginException, NetworkException, UnexpectedResponseException


class GuestAo3Session(Ao3SessionAPI):
    """
    AO3 guest session object
    """

    is_authed: bool
    authenticity_token: Optional[str]
    username: str
    session: requests.Session

    def __init__(self, username: str = "") -> None:
        """
        Startup a session object.
        """
        super().__init__()

        self.is_authed = False
        self.authenticity_token = None
        self.username = username
        self.session = requests.Session()

    @property
    def user(self) -> User:
        """
        Protect the User property from eternal set.

        :return:
        """
        return User(self.username, self, False)

    @threadable.threadable
    def comment(
        self,
        commentable: Union[WorkAPI, "Chapter"],
        comment_text: str,
        oneshot: bool = False,
        commentid: Optional[Union[str, int]] = None,
    ) -> requests.models.Response:
        """Leaves a comment on a specific work.

        This function is threadable.

        Args:
            commentable (Work/Chapter): Commentable object
            comment_text (str): Comment text (must have between 1 and 10000 characters)
            oneshot (bool): Should be True if the work has only one chapter. In this case, chapterid becomes workid
            commentid (str/int): If specified, the comment is posted as a reply to this one. Defaults to None.

        Raises:
            utils.InvalidIdError: Invalid ID
            utils.UnexpectedResponseError: Unknown error
            utils.PseudoError: Couldn't find a valid pseudonym to post under
            utils.DuplicateCommentError: The comment you're trying to post was already posted
            ValueError: Invalid name/email

        Returns:
            requests.models.Response: Response object
        """

        response = utils.comment(commentable, comment_text, self, oneshot, commentid)
        return response

    @threadable.threadable
    def kudos(self, work: WorkAPI) -> bool:
        """Leave a 'kudos' in a specific work.
        This function is threadable.

        Args:
            work (Work): ID of the work

        Raises:
            utils.UnexpectedResponseError: Unexpected response received
            utils.InvalidIdError: Invalid ID (work doesn't exist)

        Returns:
            bool: True if successful, False if you already left kudos there
        """

        return utils.kudos(work, self)

    @threadable.threadable
    def refresh_auth_token(self) -> None:
        """Refreshes the authenticity token.

        This function is threadable.

        Raises:
            utils.UnexpectedResponseError: Couldn't refresh the token
        """

        # For some reason, the auth token in the root path only works if you're
        # unauthenticated. To get around that, we check if this is an authed
        # session and, if so, get the token from the profile page.

        if self.is_authed:
            req = self.session.get(f"https://archiveofourown.org/users/{self.username}")
        else:
            req = self.session.get("https://archiveofourown.org")

        if req.status_code == 429:
            raise RateLimitedException(
                "We are being rate-limited. Try again in a while or reduce the number of requests"
            )

        soup = BeautifulSoup(req.content, "lxml")
        token = soup.find("input", {"name": "authenticity_token"})

        if token is None:
            input_box = soup.find("input")
            assert input_box["name"] == "authenticity_token"

            self.authenticity_token = input_box["value"]
            return

        if token is None:
            raise UnexpectedResponseException("Couldn't refresh token")

        self.authenticity_token = token.attrs["value"]

    def __del__(self) -> None:
        """
        Elegant shutdown of the session.

        :return:
        """
        self.session.close()


class Ao3SessionUnPooled(GuestAo3Session):
    """
    AO3 session object.

    Used for authenticated users.
    """

    is_authed: bool

    username: str
    # Password is deliberately not stored

    user_url: str
    login_page_url: str
    post_login_title: str

    _subscriptions_url: str
    _bookmarks_url: str
    _history_url: str

    _bookmarks: Optional[list[WorkAPI]]

    _history: Optional[list[list[WorkAPI, int, datetime.datetime]]]

    logged_in: bool = False

    session: requests.Session
    session_requester: Optional[Requester]

    def get_subscriptions_url(self, page: int = 1) -> str:
        """
        Return the subscription URL for the current user.

        :param page:
        :return:
        """
        url = self._subscriptions_url.format(self.username, page)
        return url

    def __init__(self, username: str, password: str) -> None:
        """Creates a new AO3 session object

        Args:
            username (str): AO3 username
            password (str): AO3 password

        Raises:
            utils.LoginError: Login was unsucessful (wrong username or password)
        """

        self.logged_in = False

        super().__init__(username=username)

        self.is_authed = True

        self.url = "https://archiveofourown.org/users/%s" % self.username

        self.session = requests.Session()

        login_page_url = "https://archiveofourown.org/users/login"
        soup = self.request(login_page_url, force_session=self.session)
        assert soup is not None, f"Error when getting page {login_page_url = }"

        input_box = soup.find("input")
        assert input_box is not None, f"Error finding input box during token refresh. - {soup.title.string = }"
        assert input_box["name"] == "authenticity_token"

        self.authenticity_token = input_box["value"]

        self.do_login(username=username, password=password)

    def do_login(self, username: str, password: str) -> None:
        """
        We have all the components - actually log in with this session.

        :return:
        """

        payload = {
            "user[login]": username,
            "user[password]": password,
            "authenticity_token": self.authenticity_token,
        }
        login_post_resp = self.post(
            "https://archiveofourown.org/users/login",
            params=payload,
            allow_redirects=True,
            force_session=self.session,
        )

        if login_post_resp.status_code == 429:
            raise RateLimitedException(
                "We are being rate-limited. Try again in a while or reduce the number of requests"
            )

        if (
            len(login_post_resp.history) == 1
            and not login_post_resp.history[0].status_code == 302
        ):
            raise LoginException("Invalid username or password")

        # Last check - is the page title telling us auth failed?
        content_type = login_post_resp.headers.get("content-type", "")
        charset = "utf-8"  # sensible default

        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].split(";")[0].strip()

        login_soup = BeautifulSoup(
            login_post_resp.content.decode(charset, errors="replace"), "html.parser"
        )

        title = login_soup.title.string if login_soup.title else None
        self.post_login_title = title

        if title == "Auth Error | Archive of Our Own":
            raise LoginException("Invalid username or password")

        if title == "archiveofourown.org | 525: SSL handshake failed":
            raise LoginException("525 error - probably cloudflare bug - rotate VPN exit node?")

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

        self.logged_in = True

        # Mostly for testing - just want to be sure nothing else happens too fast
        time.sleep(5)

    def request(
        self,
        url: str,
        proxies: Optional[dict[str, str]] = None,
        set_main_url_req: bool = False,
        force_session: Optional[requests.Session] = None,
    ) -> BeautifulSoup:
        """Request a web page and return a BeautifulSoup object.

        Args:
            url (str): Url to request
            proxies: Provide proxy options to the underlying call
            set_main_url_req: If True, will set the soup for the main page to this

        Returns:
            bs4.BeautifulSoup: BeautifulSoup object representing the requested page's html
        """

        forced_session = force_session if force_session is not None else self.session

        return super().request(
            url=url, proxies=proxies, set_main_url_req=set_main_url_req, force_session=forced_session
        )

    @property
    def _session(self) -> Optional["Ao3SessionAPI"]:
        """
        Hack to present the same API as most other classes.

        :return:
        """
        if self.logged_in:
            return self
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
                    workid = utils.workid_from_url(a["href"])
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
                    workid = utils.workid_from_url(a["href"])

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
                        workid = utils.workid_from_url(a["href"])

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
        h2 = div.h2.text.split()
        return int(h2[4].replace(",", ""))

    def get_statistics(self, year: Optional[int] = None) -> dict[str, int]:
        """
        Return the user's statistics for a given year.

        :param year:
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
                            works.append(Work(work_id, session=self, load=False))
                        except AttributeError:
                            pass
                    grabbed = True
                except HTTPException:
                    time.sleep(timeout_sleep)
            time.sleep(sleep)
        return works


class Ao3Session(Ao3SessionUnPooled):

    def login(self, username: str, password: str) -> None:
        """
        Logs in and transparently reuses a pooled, thread-safe session
        for this username. Multiple Session wrappers will share one underlying
        authenticated session and a per-token throttle.
        """

        def _do_login_on(sess: requests.Session) -> str:
            # 1) GET login page for token
            r = requester.get("https://archiveofourown.org/users/login", force_session=sess)
            if r.status_code != 200:
                raise NetworkException(f"GET /users/login -> {r.status_code}", url=r.url, status=r.status_code)

            token = self._parse_authenticity_token(r.text)
            if not token:
                raise LoginException("Could not find authenticity token on login page")

            payload = {
                "user[login]": username,
                "user[password]": password,
                "authenticity_token": token,
            }
            r2 = requester.post(
                "https://archiveofourown.org/users/login",
                params=payload,
                allow_redirects=False,
                force_session=sess,
            )

            # Handle redirect success (AO3 login normally 302s)
            if r2.status_code == 302:
                loc = r2.headers.get("Location")
                if not loc:
                    raise LoginException("Login redirect missing Location header")
                # follow with the same sess
                r3 = requester.get(loc, force_session=sess)
                # optionally assert logged-in state here
                return token

            # 200 likely indicates an error page with the form
            if r2.status_code == 200:
                if self._has_login_error(r2.text):
                    msg = self._extract_login_error(r2.text) or "Invalid username or password"
                    raise LoginException(msg)
                raise LoginException("Unexpected login response (200) without redirect")

            raise NetworkException(f"Login failed: {r2.status_code}", url=r2.url, status=r2.status_code)

        # Pull (or create) the shared underlying session for this user
        proxy = session_pool.get_or_create(
            username,
            login_fn=_do_login_on,
            # tune per-token throttle here if you want different limits
            token_requests_per_window=60,
            token_window_seconds=60.0,
        )

        # This wrapper now uses the pooled, thread-safe, throttled session
        self.session = proxy
        self.username = username
        self.is_authed = True
        # If you keep a token attribute on Session, reflect it:
        # (pool set_token() already applied)
        self.authenticity_token = getattr(self, "authenticity_token", None)  # optional



class PrototypeSession(GuestAo3Session):
    """
    AO3 session object.

    Used for authenticated users.
    """

    _subscriptions_url: str
    _bookmarks_url: str
    _history_url: str

    _bookmarks: Optional[list[WorkAPI]]

    _history: Optional[list[list[WorkAPI, int, datetime.datetime]]]

    logged_in: bool = False

    def __init__(self, username: str, password: str) -> None:
        """Creates a new AO3 session object

        Args:
            username (str): AO3 username
            password (str): AO3 password

        Raises:
            utils.LoginError: Login was unsucessful (wrong username or password)
        """

        self.logged_in = False

        super().__init__()

        self.is_authed = True
        self.username = username
        self.login_page_url = "https://archiveofourown.org/users/login"
        self.url = "https://archiveofourown.org/users/%s" % self.username

        self.session = requests.Session()

        self.refresh_auth_token(initial_login=True)

        payload = {
            "user[login]": username,
            "user[password]": password,
            "authenticity_token": self.authenticity_token,
        }
        login_post_resp = self.post(
            self.login_page_url,
            params=payload,
            allow_redirects=False,
            force_session=self.session,
        )
        # Fallback to allowing redirects
        # Something about the login process seems to have changed
        if login_post_resp.status_code == 302:

            login_post_resp = self.post(
                "https://archiveofourown.org/users/login",
                params=payload,
                allow_redirects=True,
                force_session=self.session,
            )

        if login_post_resp.status_code == 429:
            raise RateLimitedException(
                "We are being rate-limited. Try again in a while or reduce the number of requests"
            )

        if (
            len(login_post_resp.history) == 1
            and not login_post_resp.history[0].status_code == 302
        ):
            raise LoginException("Invalid username or password")

        # Last check - is the page title telling us auth failed?
        content_type = login_post_resp.headers.get("content-type", "")
        charset = "utf-8"  # sensible default

        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].split(";")[0].strip()

        login_soup = BeautifulSoup(
            login_post_resp.content.decode(charset, errors="replace"), "html.parser"
        )

        title = login_soup.title.string if login_soup.title else None

        if title == "Auth Error | Archive of Our Own":
            raise LoginException("Invalid username or password")

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

        self.logged_in = True

    @property
    def _session(self) -> Optional["SessionAPI"]:
        """
        Hack to present the same API as most other classes.

        :return:
        """
        if self.logged_in:
            return self
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
        url = self.get_subscriptions_url(page)

        soup = self.request(url, force_session=self.session)

        subscriptions = soup.find("dl", {"class": "subscription index group"})
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
                    workid = utils.workid_from_url(a["href"])
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
                    workid = utils.workid_from_url(a["href"])

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
                        workid = utils.workid_from_url(a["href"])

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
        h2 = div.h2.text.split()
        return int(h2[4].replace(",", ""))

    def get_statistics(self, year: Optional[int] = None) -> dict[str, int]:
        """
        Return the user's statistics for a given year.

        :param year:
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
                            works.append(Work(work_id, session=self, load=False))
                        except AttributeError:
                            pass
                    grabbed = True
                except HTTPException:
                    time.sleep(timeout_sleep)
            time.sleep(sleep)
        return works
