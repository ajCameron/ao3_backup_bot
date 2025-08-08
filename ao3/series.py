
"""
Represents a series of works on the archive.
"""

from typing import Optional, Any

from datetime import date
from functools import cached_property

from bs4 import BeautifulSoup

from ao3 import threadable, utils
from ao3.common import get_work_from_banner
from ao3.requester import requester
from ao3.users import User
from ao3.works import Work
from ao3.api.object_api import BaseObjectAPI


class Series(BaseObjectAPI):
    """
    Represent a series on the archive.
    """

    id: int

    def __init__(self, seriesid: int, session: Optional["Session"] = None, load: Optional[bool] = True):
        """Creates a new series object

        Args:
            seriesid (int/str): ID of the series
            session (AO3.Session, optional): Session object. Defaults to None.
            load (bool, optional): If true, the work is loaded on initialization. Defaults to True.

        Raises:
            utils.InvalidIdError: Invalid series ID
        """

        self.id = seriesid
        self._session = session
        self._soup = None
        if load:
            self.reload()

    def __eq__(self, other: "Series") -> bool:
        """
        Checks the other

        :param other:
        :return:
        """
        return isinstance(other, self.__class__) and other.id == self.id

    def __repr__(self) -> str:
        """
        Str rep of the class.

        :return:
        """
        try:
            return f"<Series [{self.name}]>"
        except Exception as e:
            return f"<Series [{self.id}] - [{e}]>"

    def __getstate__(self) -> dict[str, Any]:
        """
        Return the current state of the class.

        :return:
        """
        d = {}
        for attr in self.__dict__:
            if isinstance(self.__dict__[attr], BeautifulSoup):
                d[attr] = (self.__dict__[attr].encode(), True)
            else:
                d[attr] = (self.__dict__[attr], False)
        return d

    def __setstate__(self, d: dict[str, Any]):
        """
        Write the saved state back out to itself.

        :param d:
        :return:
        """
        for attr in d:
            value, issoup = d[attr]
            if issoup:
                self.__dict__[attr] = BeautifulSoup(value, "lxml")
            else:
                self.__dict__[attr] = value

    def set_session(self, session: "Session") -> None:
        """Sets the session used to make requests for this series

        Args:
            session (AO3.Session/AO3.GuestSession): session object
        """

        self._session = session

    @threadable.threadable
    def reload(self) -> None:
        """
        Loads information about this series.

        This function is threadable.
        """

        for attr in self.__class__.__dict__:
            if isinstance(getattr(self.__class__, attr), cached_property):
                if attr in self.__dict__:
                    delattr(self, attr)

        self._soup = self.request(f"https://archiveofourown.org/series/{self.id}")
        if "Error 404" in self._soup.text:
            raise utils.InvalidIdError("Cannot find series")

    @threadable.threadable
    def subscribe(self) -> None:
        """Subscribes to this series.

        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

        if self._session is None or not self._session.is_authed:
            raise utils.AuthError(
                "You can only subscribe to a series using an authenticated session"
            )

        utils.subscribe(self, "Series", self._session)

    @threadable.threadable
    def unsubscribe(self) -> None:
        """Unubscribes from this series.

        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

        if not self.is_subscribed:
            raise Exception("You are not subscribed to this series")
        if self._session is None or not self._session.is_authed:
            raise utils.AuthError(
                "You can only unsubscribe from a series using an authenticated session"
            )

        utils.subscribe(self, "Series", self._session, True, self._sub_id)

    @threadable.threadable
    def bookmark(
        self,
        notes: Optional[str] = "",
        tags: Optional[list[str]] = None,
        collections: Optional[list[str]] = None,
        private: Optional[bool] = False,
        recommend: Optional[bool] = False,
        pseud: Optional[str]=None,
    ) -> None:
        """Bookmarks this series.

        This function is threadable

        Args:
            notes (str, optional): Bookmark notes. Defaults to "".
            tags (list, optional): What tags to add. Defaults to None.
            collections (list, optional): What collections to add this bookmark to. Defaults to None.
            private (bool, optional): Whether this bookmark should be private. Defaults to False.
            recommend (bool, optional): Whether to recommend this bookmark. Defaults to False.
            pseud (str, optional): What pseud to add the bookmark under. Defaults to default pseud.

        Raises:
            utils.UnloadedError: Series isn't loaded
            utils.AuthError: Invalid session
        """

        if not self.loaded:
            raise utils.UnloadedError(
                "Series isn't loaded. Have you tried calling Series.reload()?"
            )

        if self._session is None:
            raise utils.AuthError("Invalid session")

        utils.bookmark(
            self, self._session, notes, tags, collections, private, recommend, pseud
        )

    @threadable.threadable
    def delete_bookmark(self) -> None:
        """Removes a bookmark from this series.

        This function is threadable

        Raises:
            utils.UnloadedError: Series isn't loaded
            utils.AuthError: Invalid session
        """

        if not self.loaded:
            raise utils.UnloadedError(
                "Series isn't loaded. Have you tried calling Series.reload()?"
            )

        if self._session is None:
            raise utils.AuthError("Invalid session")

        if self._bookmarkid is None:
            raise utils.BookmarkError("You don't have a bookmark here")

        utils.delete_bookmark(self._bookmarkid, self._session, self.authenticity_token)

    @cached_property
    def _bookmarkid(self) -> Optional[int]:
        """
        If this series is bookmarked, get the id of that bookmark.

        :return:
        """
        form_div = self._soup.find("div", {"id": "bookmark-form"})
        if form_div is None:
            return None
        if form_div.form is None:
            return None
        if "action" in form_div.form and form_div.form["action"].startswith(
            "/bookmark"
        ):
            text = form_div.form["action"].split("/")[-1]
            if text.isdigit():
                return int(text)
            return None
        return None

    @cached_property
    def url(self) -> str:
        """Returns the URL to this series.

        Returns:
            str: series URL
        """

        return f"https://archiveofourown.org/series/{self.id}"

    @property
    def loaded(self) -> bool:
        """Returns True if this series has been loaded"""
        return self._soup is not None

    @cached_property
    def authenticity_token(self) -> Optional[str]:
        """Token used to take actions that involve this work."""

        if not self.loaded:
            return None

        token = self._soup.find("meta", {"name": "csrf-token"})
        return token["content"]

    @cached_property
    def is_subscribed(self) -> bool:
        """True if you're subscribed to this series"""

        if self._session is None or not self._session.is_authed:
            raise utils.AuthError(
                "You can only get a series ID using an authenticated session"
            )

        form = self._soup.find("form", {"data-create-value": "Subscribe"})
        input_ = form.find("input", {"name": "commit", "value": "Unsubscribe"})
        return input_ is not None

    @cached_property
    def _sub_id(self) -> int:
        """Returns the subscription ID. Used for unsubscribing.


        Raises:
            :exception If you are not subscribed to this series

        """

        if not self.is_subscribed:
            raise Exception("You are not subscribed to this series")

        form = self._soup.find("form", {"data-create-value": "Subscribe"})
        id_ = form.attrs["action"].split("/")[-1]
        return int(id_)

    @cached_property
    def name(self) -> str:
        """
        Return the series name as a string.

        :return:
        """
        div = self._soup.find("div", {"class": "series-show region"})
        return div.h2.getText().replace("\t", "").replace("\n", "")

    @cached_property
    def creators(self) -> list[User]:
        """
        Return the creators of the series.

        :return:
        """
        dl = self._soup.find("dl", {"class": "series meta group"})
        return [
            User(author.getText(), load=False)
            for author in dl.findAll("a", {"rel": "author"})
        ]

    @cached_property
    def series_begun(self) -> date:
        """
        Returns a date time object for when the series begun.

        :return:
        """
        dl = self._soup.find("dl", {"class": "series meta group"})
        info = dl.findAll(("dd", "dt"))
        last_dt = None
        date_str = None
        for field in info:
            if field.name == "dt":
                last_dt = field.getText().strip()
            elif last_dt == "Series Begun:":
                date_str = field.getText().strip()
                break
        if date_str is None:
            raise utils.HTTPError("Couldn't find the date in the HTML.")
        return date(*list(map(int, date_str.split("-"))))

    @cached_property
    def series_updated(self) -> date:
        """
        Returns a datetime object for when the series last updated.

        :return series_update_date:
        :raise utils.HTTPError:
        """
        dl = self._soup.find("dl", {"class": "series meta group"})
        info = dl.findAll(("dd", "dt"))
        last_dt = None
        date_str = None
        for field in info:
            if field.name == "dt":
                last_dt = field.getText().strip()
            elif last_dt == "Series Updated:":
                date_str = field.getText().strip()
                break

        if date_str is None:
            raise utils.HTTPError("Couldn't find the date in the HTML.")

        return date(*list(map(int, date_str.split("-"))))

    @cached_property
    def words(self) -> int:
        """
        Find the word count for the series.

        :return:
        """
        dl = self._soup.find("dl", {"class": "series meta group"})
        stats = dl.find("dl", {"class": "stats"}).findAll(("dd", "dt"))
        last_dt = None
        words = None
        for field in stats:
            if field.name == "dt":
                last_dt = field.getText().strip()
            elif last_dt == "Words:":
                words = field.getText().strip()
                break

        if words is None:
            raise utils.HTTPError("Couldn't find the word count in the HTML.")

        return int(words.replace(",", ""))

    @cached_property
    def nworks(self) -> int:
        """
        Returns the number of works in the series.

        :return:
        """
        dl = self._soup.find("dl", {"class": "series meta group"})
        stats = dl.find("dl", {"class": "stats"}).findAll(("dd", "dt"))
        last_dt = None
        works = None
        for field in stats:
            if field.name == "dt":
                last_dt = field.getText().strip()
            elif last_dt == "Works:":
                works = field.getText().strip()
                break

        if works is None:
            raise utils.HTTPError("Couldn't find the works count in the HTML.")

        return int(works.replace(",", ""))

    @cached_property
    def complete(self):
        dl = self._soup.find("dl", {"class": "series meta group"})
        stats = dl.find("dl", {"class": "stats"}).findAll(("dd", "dt"))
        last_dt = None
        complete: Optional[str] = None
        for field in stats:
            if field.name == "dt":
                last_dt = field.getText().strip()
            elif last_dt == "Complete:":
                complete = field.getText().strip()
                break

        if complete is None:
            raise utils.HTTPError("Couldn't find the complete flag in the HTML.")

        return True if complete == "Yes" else False

    @cached_property
    def description(self) -> str:
        """
        Description of the series.

        :return:
        """
        dl = self._soup.find("dl", {"class": "series meta group"})
        info = dl.findAll(("dd", "dt"))
        last_dt = None
        desc = ""
        for field in info:
            if field.name == "dt":
                last_dt = field.getText().strip()
            elif last_dt == "Description:":
                desc = field.getText().strip()
                break
        return desc

    @cached_property
    def notes(self) -> str:
        """
        Notes attatched to this series.

        :return:
        """
        dl = self._soup.find("dl", {"class": "series meta group"})
        info = dl.findAll(("dd", "dt"))
        last_dt = None
        notes = ""
        for field in info:
            if field.name == "dt":
                last_dt = field.getText().strip()
            elif last_dt == "Notes:":
                notes = field.getText().strip()
                break
        return notes

    @cached_property
    def nbookmarks(self) -> int:
        """
        Bookmark count for this series.

        :return:
        """
        dl = self._soup.find("dl", {"class": "series meta group"})
        stats = dl.find("dl", {"class": "stats"}).findAll(("dd", "dt"))
        last_dt = None
        book = "0"
        for field in stats:
            if field.name == "dt":
                last_dt = field.getText().strip()
            elif last_dt == "Bookmarks:":
                book = field.getText().strip()
                break
        return int(book.replace(",", ""))

    @cached_property
    def work_list(self) -> list[Work]:
        """
        List of works in this series.

        :return:
        """
        ul = self._soup.find("ul", {"class": "series work index group"})
        works = []
        for work in ul.find_all("li", {"role": "article"}):
            if work.h4 is None:
                continue
            works.append(get_work_from_banner(work))
        #     authors = []
        #     if work.h4 is None:
        #         continue
        #     for a in work.h4.find_all("a"):
        #         if "rel" in a.attrs.keys():
        #             if "author" in a["rel"]:
        #                 authors.append(User(a.string, load=False))
        #         elif a.attrs["href"].startswith("/works"):
        #             workname = a.string
        #             workid = utils.workid_from_url(a["href"])
        #     new = Work(workid, load=False)
        #     setattr(new, "title", workname)
        #     setattr(new, "authors", authors)
        #     works.append(new)
        return works
