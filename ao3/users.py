"""
Represents users of the archive.

They can author works, series, all manner of stuff.
Someone should probably look into them.
"""

from functools import cached_property

from typing import Optional

import ao3.errors
from ao3 import threadable, utils
from ao3.common import get_work_from_banner
from ao3.api.object_api import BaseObjectAPI
from ao3.api.comment_session_work_api import WorkAPI


class User(BaseObjectAPI):
    """
    AO3 user object
    """

    def __init__(
        self, username: str, session: Optional["Session"] = None, load: bool = True
    ):
        """Creates a new AO3 user object

        Args:
            username (str): AO3 username
            session (AO3.Session, optional): Used to access additional info
            load (bool, optional): If true, the user is loaded on initialization. Defaults to True.
        """

        super().__init__()

        self.username = username
        self._session = session
        self._soup_works = None
        self._soup_profile = None
        self._soup_bookmarks = None
        self._works = None
        self._bookmarks = None
        if load:
            self.reload()

    def __repr__(self) -> str:
        """
        String rep of the class.

        :return:
        """
        return f"<User [{self.username}]>"

    def __eq__(self, other: "User") -> bool:
        """
        Check to see if this user is equivilent to the other.

        :param other:
        :return:
        """
        return isinstance(other, self.__class__) and other.username == self.username

    def set_session(self, session: "Session") -> None:
        """Sets the session used to make requests for this work

        Args:
            session (AO3.Session/AO3.GuestSession): session object
        """

        self._session = session

    @threadable.threadable
    def reload(self) -> None:
        """
        Loads information about this user.

        This function is threadable.
        """

        for attr in self.__class__.__dict__:
            if isinstance(getattr(self.__class__, attr), cached_property):
                if attr in self.__dict__:
                    delattr(self, attr)

        @threadable.threadable
        def req_works(username: str) -> None:
            """
            Update the user works soup - for later parsing.

            :param username:
            :return:
            """
            self._soup_works = self.request(
                f"https://archiveofourown.org/users/{username}/works"
            )
            token = self._soup_works.find("meta", {"name": "csrf-token"})
            setattr(self, "authenticity_token", token["content"])

        @threadable.threadable
        def req_profile(username: str) -> None:
            """
            Update the profile page soup - for later parsing.

            :param username:
            :return:
            """
            self._soup_profile = self.request(
                f"https://archiveofourown.org/users/{username}/profile"
            )
            token = self._soup_profile.find("meta", {"name": "csrf-token"})
            setattr(self, "authenticity_token", token["content"])

        @threadable.threadable
        def req_bookmarks(username: str) -> None:
            """
            Update the user booksmarks soup - for later parsing.

            :param username:
            :return:
            """
            self._soup_bookmarks = self.request(
                f"https://archiveofourown.org/users/{username}/bookmarks"
            )
            token = self._soup_bookmarks.find("meta", {"name": "csrf-token"})
            setattr(self, "authenticity_token", token["content"])

        rs = [
            req_works(self.username, threaded=True),
            req_profile(self.username, threaded=True),
            req_bookmarks(self.username, threaded=True),
        ]
        for r in rs:
            r.join()

        self._works = None
        self._bookmarks = None

    def get_avatar(self) -> tuple[str, bytes]:
        """Returns a tuple containing the avatar name of the file and its data.

        Returns:
            tuple: (name: str, img: bytes)
        """

        icon = self._soup_profile.find("p", {"class": "icon"})
        src = icon.img.attrs["src"]
        name = src.split("/")[-1].split("?")[0]
        img = self.get(src).content
        return name, img

    @threadable.threadable
    def subscribe(self) -> None:
        """Subscribes to this user.

        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

        if self._session is None or not self._session.is_authed:
            raise errors.AuthException(
                "You can only subscribe to a user using an authenticated session"
            )

        utils.subscribe(self, "User", self._session)

    @threadable.threadable
    def unsubscribe(self) -> None:
        """Unubscribes from this user.

        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

        if not self.is_subscribed:
            raise Exception("You are not subscribed to this user")
        if self._session is None or not self._session.is_authed:
            raise errors.AuthException(
                "You can only unsubscribe from a user using an authenticated session"
            )

        utils.subscribe(self, "User", self._session, True, self._sub_id)

    @property
    def id(self) -> Optional[int]:
        """
        Return the subscribable id of this user - if it has one.

        :return:
        """
        id_ = self._soup_profile.find("input", {"id": "subscription_subscribable_id"})
        return int(id_["value"]) if id_ is not None else None

    @cached_property
    def is_subscribed(self) -> bool:
        """True if you're subscribed to this user."""

        if self._session is None or not self._session.is_authed:
            raise errors.AuthException(
                "You can only get a user ID using an authenticated session"
            )

        header = self._soup_profile.find("div", {"class": "primary header module"})
        input_ = header.find("input", {"name": "commit", "value": "Unsubscribe"})
        return input_ is not None

    @property
    def loaded(self) -> bool:
        """Returns True if this user has been loaded."""
        return self._soup_profile is not None

    # @cached_property
    # def authenticity_token(self):
    #     """Token used to take actions that involve this user"""

    #     if not self.loaded:
    #         return None

    #     token = self._soup_profile.find("meta", {"name": "csrf-token"})
    #     return token["content"]

    @cached_property
    def user_id(self) -> int:
        """
        This is different from the id for some reason.

        :return:
        """
        if self._session is None or not self._session.is_authed:
            raise errors.AuthException(
                "You can only get a user ID using an authenticated session"
            )

        header = self._soup_profile.find("div", {"class": "primary header module"})
        input_ = header.find("input", {"name": "subscription[subscribable_id]"})
        if input_ is None:
            raise errors.UnexpectedResponseException("Couldn't fetch user ID")
        return int(input_.attrs["value"])

    @cached_property
    def _sub_id(self) -> int:
        """Returns the subscription ID.

        Used for unsubscribing."""

        if not self.is_subscribed:
            raise Exception("You are not subscribed to this user")

        header = self._soup_profile.find("div", {"class": "primary header module"})
        id_ = header.form.attrs["action"].split("/")[-1]
        return int(id_)

    @cached_property
    def works(self) -> int:
        """Returns the number of works authored by this user.

        Not a list of the works - as you might expect!

        Returns:
            int: Number of works
        """

        div = self._soup_works.find(
            "div", {"class": "works-index dashboard filtered region"}
        )
        h2 = div.h2.text.split()
        return int(h2[4].replace(",", ""))

    @cached_property
    def _works_pages(self) -> int:
        """
        Returns the number of pages of works that need to be gone through.

        :return:
        """
        pages = self._soup_works.find("ol", {"title": "pagination"})
        if pages is None:
            return 1
        n = 1
        for li in pages.findAll("li"):
            text = li.getText()
            if text.isdigit():
                n = int(text)
        return n

    def get_works(self, use_threading: bool = False) -> list["WorkAPI"]:
        """
        Get works authored by this user.

        Returns:
            list: List of works
        """

        if self._works is None:
            if use_threading:
                self.load_works_threaded()
            else:
                self._works = []
                for page in range(self._works_pages):
                    self._load_works(page=page + 1)
        return self._works

    @threadable.threadable
    def load_works_threaded(self) -> None:
        """
        Get the user's works using threads.

        This function is threadable.
        """

        threads = []
        self._works = []
        for page in range(self._works_pages):
            threads.append(self._load_works(page=page + 1, threaded=True))
        for thread in threads:
            thread.join()

    @threadable.threadable
    def _load_works(self, page: int = 1) -> None:
        """
        Load the user's works from a specified page.

        :param page:
        :return None: All changes are internal to the cache.
        """

        self._soup_works = self.request(
            f"https://archiveofourown.org/users/{self.username}/works?page={page}"
        )

        ol = self._soup_works.find("ol", {"class": "work index group"})

        for work in ol.find_all("li", {"role": "article"}):
            if work.h4 is None:
                continue
            self._works.append(get_work_from_banner(work))

    @cached_property
    def bookmarks(self) -> int:
        """Returns the number of works user has bookmarked

        Returns:
            int: Number of bookmarks
        """

        div = self._soup_bookmarks.find(
            "div", {"class": "bookmarks-index dashboard filtered region"}
        )
        h2 = div.h2.text.split()
        return int(h2[4].replace(",", ""))

    @cached_property
    def _bookmarks_pages(self) -> int:
        """
        Returns the number of pages of bookmarks the user has.

        :return:
        """
        pages = self._soup_bookmarks.find("ol", {"title": "pagination"})
        if pages is None:
            return 1
        n = 1
        for li in pages.findAll("li"):
            text = li.getText()
            if text.isdigit():
                n = int(text)
        return n

    def get_bookmarks(self, use_threading: bool = False) -> list["WorkAPI"]:
        """
        Get this user's bookmarked works. Loads them if they haven't been previously

        Returns:
            list: List of works
        """

        if self._bookmarks is None:
            if use_threading:
                self.load_bookmarks_threaded()
            else:
                self._bookmarks = []
                for page in range(self._bookmarks_pages):
                    self._load_bookmarks(page=page + 1)
        return self._bookmarks

    @threadable.threadable
    def load_bookmarks_threaded(self) -> None:
        """
        Get the user's bookmarks using threads.

        This function is threadable.
        """

        threads = []
        self._bookmarks = []
        for page in range(self._bookmarks_pages):
            threads.append(self._load_bookmarks(page=page + 1, threaded=True))
        for thread in threads:
            thread.join()

    @threadable.threadable
    def _load_bookmarks(self, page: int = 1) -> None:
        """
        Load a page of the user's bookmarks.

        :param page:
        :return None: All changes to internal cache
        """
        self._soup_bookmarks = self.request(
            f"https://archiveofourown.org/users/{self.username}/bookmarks?page={page}"
        )

        ol = self._soup_bookmarks.find("ol", {"class": "bookmark index group"})

        for work in ol.find_all("li", {"role": "article"}):
            if work.h4 is None:
                continue
            self._bookmarks.append(get_work_from_banner(work))

    @cached_property
    def bio(self) -> str:
        """Returns the user's bio

        Returns:
            str: User's bio
        """

        div = self._soup_profile.find("div", {"class": "bio module"})
        if div is None:
            return ""
        blockquote = div.find("blockquote", {"class": "userstuff"})
        return blockquote.getText() if blockquote is not None else ""

    @cached_property
    def url(self) -> str:
        """Returns the URL to the user's profile

        Returns:
            str: user profile URL
        """

        return "https://archiveofourown.org/users/%s" % self.username

    @staticmethod
    def str_format(string: str) -> str:
        """Formats a given string

        Args:
            string (str): String to format

        Returns:
            str: Formatted string
        """

        return string.replace(",", "")

    @property
    def work_pages(self) -> int:
        """
        Returns how many pages of works a user has

        Returns:
            int: Amount of pages
        """
        return self._works_pages
