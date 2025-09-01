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
from ao3.errors import LoginException, NetworkException, UnexpectedResponseException, AuthException


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

    _bookmarks_url: str
    _history_url: str

    _bookmarks: Optional[list[WorkAPI]]

    _history: Optional[list[list[WorkAPI, int, datetime.datetime]]]

    logged_in: bool = False

    session: requests.Session
    session_requester: Optional[Requester]

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
        self.session_requester = Requester()
        self.session_requester.attach_session(self.session)

        login_page_url = "https://archiveofourown.org/users/login"
        soup = self.request(login_page_url, force_session=self.session_requester)
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
            raise AuthException("Invalid username or password")

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


