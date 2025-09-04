"""
API for the work class - declared here to avoid circular imports.

This is (largely) and extended typing thing.
You can use this as a proxy for the Work object, when using the object directly would trigger a circular import.
"""

import abc
import datetime

from typing import Optional, Union, Any, Literal, Iterator
from functools import cached_property

import bs4
import requests

from bs4 import BeautifulSoup

from ao3.api.object_api import BaseObjectAPI
from ao3 import threadable


class WorkAPI(BaseObjectAPI, abc.ABC):
    """
    API (and common methods) for the Work object.
    """

    chapters: list["Chapter"]
    id: int
    _soup: Optional[BeautifulSoup]
    _main_page_rep: Optional[requests.Response]
    _session: "Ao3SessionAPI"

    _initial_load: bool
    _initial_chapter_load: bool

    def __init__(
        self,
        workid: int,
        session: "Ao3SessionAPI" = None,
        load: bool = True,
        load_chapters: bool = True,
    ) -> None:

        self._session = session
        self.chapters = []
        self.id = workid
        self._soup = None
        self._main_page_rep = None

        self._initial_load = load
        self._initial_chapter_load = load_chapters

    @abc.abstractmethod
    def __repr__(self) -> str:
        """
        Str rep of the class.

        :return:
        """

    @abc.abstractmethod
    def __eq__(self, other: "WorkAPI") -> bool:
        """
        Check two works are equivalent.

        Just checks id - doesn't check load state e.t.c.
        :param other:
        :return:
        """

    @abc.abstractmethod
    @threadable.threadable
    def reload(self, load_chapters: Optional[bool] = True):
        """
        Loads information about this work.

        This function is threadable.

        Args:
            load_chapters (bool, optional):
            If false, chapter text won't be parsed, and Work.load_chapters() will have to be called.
            Defaults to True.
        """

    @abc.abstractmethod
    def set_session(self, session: "Ao3SessionAPI") -> None:
        """Sets the session used to make requests for this work

        Args:
            session (AO3.Session/AO3.GuestSession): session object
        """

        self._session = session

    @property
    def session(self) -> "Ao3SessionAPI":
        """
        Access the internal session object.

        Setter is not provided - use set_session instead.
        :return:
        """
        return self._session

    @abc.abstractmethod
    def load_chapters(self) -> None:
        """
        Loads chapter objects for each one of this work's chapters.

        """

    @abc.abstractmethod
    def get_images(self) -> dict[int, tuple[tuple[str, int], ...]]:
        """Gets all images from this work

        Raises:
            utils.UnloadedError: Raises this error if the work isn't loaded

        Returns:
            dict: key = chapter_n;
                  value = tuple: Pairs of image urls and the paragraph number
                  (from a call to chapter.get_images)
        """

    @abc.abstractmethod
    def download(self, filetype: str = "PDF") -> bytes:
        """Downloads this work

        Args:
            filetype (str, optional): Desired filetype. Defaults to "PDF".
            Known filetypes are: AZW3, EPUB, HTML, MOBI, PDF.

        Raises:
            utils.DownloadError: Raised if there was an error with the download
            utils.UnexpectedResponseError: Raised if the filetype is not available for download

        Returns:
            bytes: File content
        """

    @threadable.threadable
    @abc.abstractmethod
    def download_to_file(self, filename: str, filetype: str = "EPUB") -> None:
        """
        Downloads this work and saves it in the specified file.

        This function is threadable.

        Args:
            filename (str): Name of the resulting file
            filetype (str, optional): Desired filetype. Defaults to "PDF".
            Known filetypes are: AZW3, EPUB, HTML, MOBI, PDF.

        Raises:
            utils.DownloadError: Raised if there was an error with the download
            utils.UnexpectedResponseError: Raised if the filetype is not available for download
        """

    @property
    @abc.abstractmethod
    def metadata(self) -> dict[str, Union[list[str], str]]:
        """
        Return a metadata dict for the Work.

        :return:
        """

    @abc.abstractmethod
    def get_comments(self, maximum: Optional[int] = None) -> list["Comment"]:
        """Returns a list of all threads of comments in the work. This operation can take a very long time.
        Because of that, it is recomended that you set a maximum number of comments.
        Duration: ~ (0.13 * n_comments) seconds or 2.9 seconds per comment page

        Args:
            maximum (int, optional): Maximum number of comments to be returned. None -> No maximum

        Raises:
            ValueError: Invalid chapter number
            IndexError: Invalid chapter number
            utils.UnloadedError: Work isn't loaded

        Returns:
            list: List of comments
        """

    @threadable.threadable
    @abc.abstractmethod
    def subscribe(self):
        """Subscribes to this work.
        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

    @threadable.threadable
    @abc.abstractmethod
    def unsubscribe(self) -> None:
        """Unubscribes from this user.

        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

    @cached_property
    @abc.abstractmethod
    def text(self) -> str:
        """This work's text."""

    @cached_property
    @abc.abstractmethod
    def authenticity_token(self) -> Optional[str]:
        """Token used to take actions that involve this work."""

    @cached_property
    @abc.abstractmethod
    def is_subscribed(self) -> bool:
        """True if you're subscribed to this work."""

    @cached_property
    @abc.abstractmethod
    def _sub_id(self) -> Optional[int]:
        """Returns the subscription ID. Used for unsubscribing."""

    @threadable.threadable
    @abc.abstractmethod
    def leave_kudos(self) -> bool:
        """Leave a "kudos" in this work.
        This function is threadable.

        Raises:
            utils.UnexpectedResponseError: Unexpected response received
            utils.InvalidIdError: Invalid ID (work doesn't exist)
            utils.AuthError: Invalid session or authenticity token

        Returns:
            bool: True if successful, False if you already left kudos there
        """

    @threadable.threadable
    @abc.abstractmethod
    def comment(
        self,
        comment_text: str,
        email: Optional[str] = "",
        name: Optional[str] = "",
        pseud: Optional[str] = None,
    ) -> requests.models.Response:
        """Leaves a comment on this work.
        This function is threadable.

        Args:
            comment_text (str): Comment text
            email (str, optional): Email to add comment. Needed if not logged in.
            name (str, optional): Name to add comment under. Needed if not logged in.
            pseud (str, optional): Pseud to add the comment under. Defaults to default pseud.

        Raises:
            utils.UnloadedError: Couldn't load chapters
            utils.AuthError: Invalid session

        Returns:
            requests.models.Response: Response object
        """

    @threadable.threadable
    @abc.abstractmethod
    def bookmark(
        self,
        notes: Optional[str] = "",
        tags: Optional[list[str]] = None,
        collections: Optional[list[str]] = None,
        private: Optional[bool] = False,
        recommend: Optional[bool] = False,
        pseud: Optional[str] = None,
    ) -> None:
        """Bookmarks this work
        This function is threadable

        Args:
            notes (str, optional): Bookmark notes. Defaults to "".
            tags (list, optional): What tags to add. Defaults to None.
            collections (list, optional): What collections to add this bookmark to. Defaults to None.
            private (bool, optional): Whether this bookmark should be private. Defaults to False.
            recommend (bool, optional): Whether to recommend this bookmark. Defaults to False.
            pseud (str, optional): What pseud to add the bookmark under. Defaults to default pseud.

        Raises:
            utils.UnloadedError: Work isn't loaded
            utils.AuthError: Invalid session
        """

    @threadable.threadable
    @abc.abstractmethod
    def delete_bookmark(self) -> None:
        """Removes a bookmark from this work
        This function is threadable

        Raises:
            utils.UnloadedError: Work isn't loaded
            utils.AuthError: Invalid session
        """

    @threadable.threadable
    @abc.abstractmethod
    def collect(self, collections) -> None:
        """Invites/collects this work to a collection or collections.

        This function is threadable

        Args:
            collections (list): What collections to add this work to. Defaults to None.

        Raises:
            utils.UnloadedError: Work isn't loaded
            utils.AuthError: Invalid session
        """

    @cached_property
    @abc.abstractmethod
    def _bookmarkid(self) -> Optional[int]:
        """
        Return the id of the specific bookmark.

        :return:
        """

    @property
    @abc.abstractmethod
    def loaded(self) -> bool:
        """Returns True if this work has been loaded."""

    @property
    @abc.abstractmethod
    def oneshot(self):
        """Returns True if this work has only one chapter."""

    @cached_property
    @abc.abstractmethod
    def series(self) -> list["Series"]:
        """Returns the series this work belongs to."""

    @cached_property
    @abc.abstractmethod
    def authors(self) -> list["User"]:
        """Returns the list of the work's author

        Returns:
            list: list of authors
        """

    @cached_property
    @abc.abstractmethod
    def nchapters(self) -> Optional[int]:
        """Returns the number of chapters of this work

        Returns:
            int: number of chapters
        """

    @cached_property
    @abc.abstractmethod
    def expected_chapters(self) -> Optional[int]:
        """Returns the number of expected chapters for this work, or None if
        the author hasn't provided an expected number.

        Returns:
            int: number of chapters
        """

    @property
    @abc.abstractmethod
    def status(self) -> Union[Literal["Completed"], Literal["Work in Progress"]]:
        """Returns the status of this work.

        Returns:
            str: work status
        """

    @cached_property
    @abc.abstractmethod
    def hits(self) -> int:
        """Returns the number of hits this work has

        Returns:
            int: number of hits
        """

    @cached_property
    @abc.abstractmethod
    def kudos(self) -> int:
        """Returns the number of kudos this work has

        Returns:
            int: number of kudos
        """

    @cached_property
    @abc.abstractmethod
    def comments(self) -> int:
        """Returns the number of comments this work has

        Returns:
            int: number of comments
        """

    @cached_property
    @abc.abstractmethod
    def restricted(self) -> bool:
        """Whether this is a restricted work or not

        Returns:
            bool: True if work is restricted
        """

    @cached_property
    @abc.abstractmethod
    def words(self) -> int:
        """Returns the this work's word count

        Returns:
            int: number of words
        """

    @cached_property
    @abc.abstractmethod
    def language(self) -> str:
        """Returns this work's language

        Returns:
            str: Language
        """

    @cached_property
    @abc.abstractmethod
    def bookmarks(self) -> int:
        """Returns the number of bookmarks this work has

        Returns:
            int: number of bookmarks
        """

    @cached_property
    @abc.abstractmethod
    def title(self) -> str:
        """Returns the title of this work

        Returns:
            str: work title
        """

    @cached_property
    @abc.abstractmethod
    def date_published(self) -> datetime.date:
        """Returns the date this work was published

        Returns:
            datetime.date: publish date
        """

    @cached_property
    @abc.abstractmethod
    def date_edited(self) -> datetime.date:
        """Returns the date this work was last edited.

        Returns:
            datetime.datetime: edit date
        """

    @cached_property
    @abc.abstractmethod
    def date_updated(self) -> datetime.date:
        """Returns the date this work was last updated

        Returns:
            datetime.datetime: update date
        """

    @cached_property
    @abc.abstractmethod
    def tags(self) -> list[str]:
        """Returns all the work's tags

        Returns:
            list: List of tags
        """

    @cached_property
    @abc.abstractmethod
    def characters(self) -> list[str]:
        """Returns all the work's characters

        Returns:
            list: List of characters
        """

    @cached_property
    @abc.abstractmethod
    def relationships(self) -> list[str]:
        """Returns all the work's relationships

        Returns:
            list: List of relationships
        """

    @cached_property
    @abc.abstractmethod
    def fandoms(self) -> list[str]:
        """Returns all the work's fandoms

        Returns:
            list: List of fandoms
        """

    @cached_property
    @abc.abstractmethod
    def categories(self) -> list[str]:
        """Returns all the work's categories

        Returns:
            list: List of categories
        """

    @cached_property
    @abc.abstractmethod
    def warnings(self) -> list[str]:
        """Returns all the work's warnings

        Returns:
            list: List of warnings
        """

    @cached_property
    @abc.abstractmethod
    def rating(self) -> Optional[str]:
        """Returns this work's rating

        Returns:
            str: Rating
        """

    @cached_property
    @abc.abstractmethod
    def summary(self):
        """Returns this work's summary

        Returns:
            str: Summary
        """

    @cached_property
    @abc.abstractmethod
    def start_notes(self) -> str:
        """Text from this work's start notes."""

    @cached_property
    @abc.abstractmethod
    def end_notes(self) -> str:
        """Text from this work's end notes."""

    @cached_property
    @abc.abstractmethod
    def url(self) -> str:
        """Returns the URL to this work.

        Returns:
            str: work URL
        """

    @cached_property
    @abc.abstractmethod
    def complete(self) -> bool:
        """
        Return True if the work is complete

        Retuns:
            bool: True if a work is complete
        """

    @cached_property
    @abc.abstractmethod
    def collections(self) -> list[str]:
        """Returns all the collections the work belongs to

        Returns:
            list: List of collections
        """


class Ao3SessionAPI(BaseObjectAPI, abc.ABC):
    """
    Base API for the Session object - used for type hinting.
    """

    is_authed: bool
    authenticity_token: Optional[str]
    username: str
    session: requests.Session

    def __init__(self) -> None:
        """
        Startup a session object.
        """
        self.logged_in = False

    @property
    @abc.abstractmethod
    def user(self) -> "User":
        """
        Protect the User property from eternal set.

        :return:
        """

    @threadable.threadable
    @abc.abstractmethod
    def comment(
        self,
        commentable: Union["WorkAPI", "Chapter"],
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

    @threadable.threadable
    @abc.abstractmethod
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

    @threadable.threadable
    @abc.abstractmethod
    def refresh_auth_token(self) -> None:
        """Refreshes the authenticity token.

        This function is threadable.

        Raises:
            utils.UnexpectedResponseError: Couldn't refresh the token
        """


class CommentAPI(abc.ABC):
    """
    API for the comment class.
    """

    id: Union[str, int]
    parent: Optional[Union["WorkAPI", "Chapter"]]
    parent_comment: Optional["CommentAPI"]
    _session: Optional["Ao3SessionAPI"]
    __soup: Optional[BeautifulSoup]
    load: bool

    def __init__(
        self,
        comment_id: Union[str, int],
        parent: Optional[Union["WorkAPI", "Chapter"]] = None,
        parent_comment: Optional["CommentAPI"] = None,
        session: Optional["Ao3SessionAPI"] = None,
        load: bool = True,
    ):
        """Creates a new AO3 comment object

        Args:
            comment_id (int/str): Comment ID
            parent (Work/Chapter, optional): Parent object (where the comment is posted). Defaults to None.
            parent_comment (Comment, optional): Parent comment. Defaults to None.
            session (Session/GuestSession, optional): Session object
            load (boolean, optional):  If true, the comment is loaded on initialization. Defaults to True.
        """

        self.id = comment_id
        self.parent = parent
        self.parent_comment = parent_comment
        self.authenticity_token = None
        self._thread = None
        self._session = session
        self.__soup = None

    @abc.abstractmethod
    def __repr__(self) -> str:
        """
        String rep of the class.

        :return:
        """

    @property
    @abc.abstractmethod
    def first_parent_comment(self) -> "CommentAPI":
        """
        Return the first parent of this comment tree (which might be this comment).

        :return:
        """

    @property
    @abc.abstractmethod
    def fullwork(self) -> Optional[bool]:
        """
        Check to see if this comment is on the full work.

        :return:
        """

    @cached_property
    @abc.abstractmethod
    def author(self) -> Optional["User"]:
        """Comment author."""

    @cached_property
    @abc.abstractmethod
    def text(self) -> str:
        """Comment text."""

    @abc.abstractmethod
    def get_thread(self) -> list["CommentAPI"]:
        """Returns all the replies to this comment, and all subsequent replies recursively.

        Also loads any parent comments this comment might have.

        Poorly named - could mean the thread of execution.

        Raises:
            utils.InvalidIdError: The specified comment_id was invalid

        Returns:
            list: Thread
        """

    @abc.abstractmethod
    def get_thread_iterator(self) -> Iterator["CommentAPI"]:
        """Returns a generator that allows you to iterate through the entire thread

        Returns:
            generator: The generator object
        """

    @threadable.threadable
    @abc.abstractmethod
    def reply(
        self, comment_text: str, email: str = "", name: str = ""
    ) -> requests.models.Response:
        """Replies to a comment.
        This function is threadable.

        Args:
            comment_text (str): Comment text
            email (str, optional): Email. Defaults to "".
            name (str, optional): Name. Defaults to "".

        Raises:
            utils.InvalidIdError: Invalid ID
            utils.UnexpectedResponseError: Unknown error
            utils.PseudoError: Couldn't find a valid pseudonym to post under
            utils.DuplicateCommentError: The comment you're trying to post was already posted
            ValueError: Invalid name/email
            ValueError: self.parent cannot be None

        Returns:
            requests.models.Response: Response object
        """

    @threadable.threadable
    @abc.abstractmethod
    def reload(self) -> None:
        """Loads all comment properties.

        This function is threadable.

        :return None: All changes are to the internal cache
        """

    @threadable.threadable
    @abc.abstractmethod
    def delete(self) -> None:
        """Deletes this comment.

        This function is threadable.

        Raises:
            PermissionError: You don't have permission to delete the comment
            utils.AuthError: Invalid auth token
            utils.UnexpectedResponseError: Unknown error
        """


class SeriesAPI(BaseObjectAPI):
    """
    Represent a series on the archive.
    """

    id: int
    load: bool
    _session: Ao3SessionAPI
    _soup: Optional[bs4.BeautifulSoup]

    def __init__(
        self,
        seriesid: int,
        session: Optional["Ao3SessionAPI"] = None,
        load: Optional[bool] = True,
    ):
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
        self.load = load

    @abc.abstractmethod
    def __eq__(self, other: "SeriesAPI") -> bool:
        """
        Checks the other

        :param other:
        :return:
        """

    @abc.abstractmethod
    def __repr__(self) -> str:
        """
        Str rep of the class.

        :return:
        """

    @abc.abstractmethod
    def set_session(self, session: "Ao3SessionAPI") -> None:
        """Sets the session used to make requests for this series

        Args:
            session (AO3.Session/AO3.GuestSession): session object
        """

    @threadable.threadable
    @abc.abstractmethod
    def reload(self) -> None:
        """
        Loads information about this series.

        This function is threadable.
        """

    @threadable.threadable
    @abc.abstractmethod
    def subscribe(self) -> None:
        """Subscribes to this series.

        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

    @threadable.threadable
    @abc.abstractmethod
    def unsubscribe(self) -> None:
        """Unubscribes from this series.

        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

    @threadable.threadable
    @abc.abstractmethod
    def bookmark(
        self,
        notes: Optional[str] = "",
        tags: Optional[list[str]] = None,
        collections: Optional[list[str]] = None,
        private: Optional[bool] = False,
        recommend: Optional[bool] = False,
        pseud: Optional[str] = None,
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

    @threadable.threadable
    @abc.abstractmethod
    def delete_bookmark(self) -> None:
        """Removes a bookmark from this series.

        This function is threadable

        Raises:
            utils.UnloadedError: Series isn't loaded
            utils.AuthError: Invalid session
        """

    @cached_property
    @abc.abstractmethod
    def url(self) -> str:
        """Returns the URL to this series.

        Returns:
            str: series URL
        """

    @property
    @abc.abstractmethod
    def loaded(self) -> bool:
        """Returns True if this series has been loaded."""

    @cached_property
    @abc.abstractmethod
    def authenticity_token(self) -> Optional[str]:
        """Token used to take actions that involve this work."""

    @cached_property
    @abc.abstractmethod
    def is_subscribed(self) -> bool:
        """True if you're subscribed to this series."""

    @cached_property
    @abc.abstractmethod
    def name(self) -> str:
        """
        Return the series name as a string.

        :return:
        """

    @cached_property
    @abc.abstractmethod
    def creators(self) -> list["User"]:
        """
        Return the creators of the series.

        :return:
        """

    @cached_property
    @abc.abstractmethod
    def series_begun(self) -> datetime.date:
        """
        Returns a date time object for when the series begun.

        :return:
        """

    @cached_property
    @abc.abstractmethod
    def series_updated(self) -> datetime.date:
        """
        Returns a datetime object for when the series last updated.

        :return series_update_date:
        :raise utils.HTTPError:
        """

    @cached_property
    @abc.abstractmethod
    def words(self) -> int:
        """
        Find the word count for the series.

        :return:
        """

    @cached_property
    @abc.abstractmethod
    def nworks(self) -> int:
        """
        Returns the number of works in the series.

        :return:
        """

    @cached_property
    @abc.abstractmethod
    def complete(self):
        """
        Has the series complete tags been set to True?

        :return:
        """

    @cached_property
    @abc.abstractmethod
    def description(self) -> str:
        """
        Description of the series.

        :return:
        """

    @cached_property
    @abc.abstractmethod
    def notes(self) -> str:
        """
        Notes attatched to this series.

        :return:
        """

    @cached_property
    @abc.abstractmethod
    def nbookmarks(self) -> int:
        """
        Bookmark count for this series.

        :return:
        """

    @cached_property
    @abc.abstractmethod
    def work_list(self) -> list[WorkAPI]:
        """
        List of works in this series.

        :return:
        """
