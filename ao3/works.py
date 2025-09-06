"""
Contains the "Work" class - which represents a work on AO3 and does most of the heavy lifting.
"""

from typing import Optional, Union, Literal

from datetime import datetime
from functools import cached_property

import requests
from bs4 import BeautifulSoup

import ao3.errors as errors
from ao3.api.comment_session_work_api import WorkAPI, Ao3SessionAPI, SeriesAPI
from ao3 import threadable, utils
from ao3.chapters import Chapter
from ao3.comments import Comment
from ao3.users import User
from ao3.utils import urls_match
from ao3.errors import AuthException, WorkNotFoundException, UnloadedException, HTTPException, DownloadException, UnexpectedResponseException, BookmarkException

ALLOWED_FILE_TYPES = ["AZW3", "EPUB", "HTML", "MOBI", "PDF"]


class Work(WorkAPI):
    """
    AO3 work object,
    """

    chapters: list[Chapter]
    id: int
    _soup: Optional[BeautifulSoup]
    _main_page_rep: Optional[requests.Response]
    _session: Ao3SessionAPI

    def __init__(
        self,
        workid: int,
        session: Ao3SessionAPI = None,
        load: bool = True,
        load_chapters: bool = True,
    ) -> None:
        """Creates a new AO3 work object

        Args:
            workid (int): AO3 work ID
            session (AO3.Session, optional): Used to access restricted works
            load (bool, optional): If true, the work is loaded on initialization. Defaults to True.
            load_chapters (bool, optional):

            If false, chapter text won't be parsed, and Work.load_chapters() will have to be called. Defaults to True.

        Raises:
            utils.WorkNotFoundInvalidIdError: Raised if the work wasn't found
        """

        super().__init__(
            workid=workid, session=session, load=load, load_chapters=load_chapters
        )

        if load:
            self.reload(load_chapters)

    def __repr__(self) -> str:
        """
        Str rep of the class.

        :return:
        """
        try:
            return f"<Work [{self.title}]>"
        except Exception as e:
            return f"<Work [{self.id}] - [{e}]>"

    def __eq__(self, other: "Work") -> bool:
        """
        Check two works are equivalent.

        Just checks id - doesn't check load state e.t.c.
        :param other:
        :return:
        """
        return isinstance(other, self.__class__) and other.id == self.id

    def _reload_full_text_soup(self) -> None:
        """
        Reload the full chapter text of the soup.

        :return:
        """
        # We're trying to pull the entire work into memory
        self._soup = self.request(
            f"https://archiveofourown.org/works/{self.id}?view_adult=true&view_full_work=true",
            set_main_url_req=True,
        )

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

        for attr in self.__class__.__dict__:

            if isinstance(getattr(self.__class__, attr), cached_property):
                if attr in self.__dict__:
                    delattr(self, attr)

        self._reload_full_text_soup()

        # Try and parse the chapters text out of the soup
        h2_text = self._soup.find("h2", {"class": "heading"})

        if h2_text is not None and "Error 404" in h2_text.text:
            raise WorkNotFoundException("Cannot find work")

        if load_chapters:
            self.load_chapters()

    @property
    def session(self) -> Ao3SessionAPI:
        """
        Access the internal session object.

        Setter is not provided - use set_session instead.
        :return:
        """
        return self._session

    def set_session(self, session):
        """Sets the session used to make requests for this work

        Args:
            session (AO3.Session/AO3.GuestSession): session object
        """

        self._session = session

    def load_chapters(self) -> None:
        """
        Loads chapter objects for each one of this work's chapters.

        """

        self.chapters = []

        chapters_div = self._soup.find(attrs={"id": "chapters"})

        # Unless we have an empty work, which does happen, this isn't right.
        # Try a reload.
        if chapters_div is None:
            self._reload_full_text_soup()
            chapters_div = self._soup.find(attrs={"id": "chapters"})
            if chapters_div is None:
                return

        if self.nchapters > 1:

            for n in range(1, self.nchapters + 1):

                chapter = chapters_div.find("div", {"id": f"chapter-{n}"})
                if chapter is None:
                    continue
                chapter.extract()
                preface_group = chapter.find(
                    "div", {"class": ("chapter", "preface", "group")}
                )
                if preface_group is None:
                    continue
                title = preface_group.find("h3", {"class": "title"})
                if title is None:
                    continue
                id_ = int(title.a["href"].split("/")[-1])
                c = Chapter(id_, self, self._session, False)
                c._soup = chapter
                self.chapters.append(c)

        else:
            c = Chapter(None, self, self._session, False)
            c._soup = chapters_div
            self.chapters.append(c)

    def get_images(self) -> dict[int, tuple[tuple[str, int], ...]]:
        """Gets all images from this work

        Raises:
            utils.UnloadedError: Raises this error if the work isn't loaded

        Returns:
            dict: key = chapter_n; value = chapter.get_images()
        """

        if not self.loaded:
            raise UnloadedException(
                "Work isn't loaded. Have you tried calling Work.reload()?"
            )

        chapters = {}
        for chapter in self.chapters:
            images = chapter.get_images()
            if len(images) != 0:
                chapters[chapter.number] = images
        return chapters

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
        if filetype not in ALLOWED_FILE_TYPES:
            raise DownloadException(
                f"Given type {filetype = } not in allowed types {ALLOWED_FILE_TYPES = }"
            )

        if not self.loaded:
            raise UnloadedException(
                "Work isn't loaded. Have you tried calling Work.reload()?"
            )
        download_btn = self._soup.find("li", {"class": "download"})

        if download_btn is None:
            raise AuthException(
                "Cannot find download class - you may need to log in?"
            )

        for download_type in download_btn.findAll("li"):

            if download_type.a.getText() == filetype.upper():
                url = f"https://archiveofourown.org/{download_type.a.attrs['href']}"
                req = self.get(url)
                if req.status_code == 429:
                    raise HTTPException(
                        "We are being rate-limited. Try again in a while or reduce the number of requests"
                    )

                if not req.ok:
                    raise DownloadException(
                        "An error occurred while downloading the work"
                    )
                return req.content

        raise UnexpectedResponseException(
            f"Filetype '{filetype}' is not available for download"
        )

    @threadable.threadable
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
        filetype = filetype.upper()
        assert (
            filetype in ALLOWED_FILE_TYPES
        ), f"Cannot download given filetype - {filetype} not valid."

        with open(filename, "wb") as file:
            file.write(self.download(filetype))

    @property
    def metadata(self) -> dict[str, Union[list[str], str]]:
        """
        Return a metadata dict for the Work.

        :return:
        """
        metadata = {}
        normal_fields = (
            "bookmarks",
            "categories",
            "nchapters",
            "characters",
            "complete",
            "comments",
            "expected_chapters",
            "fandoms",
            "hits",
            "kudos",
            "language",
            "rating",
            "relationships",
            "restricted",
            "status",
            "summary",
            "tags",
            "title",
            "warnings",
            "id",
            "words",
            "collections",
        )
        string_fields = (
            "date_edited",
            "date_published",
            "date_updated",
        )

        for field in string_fields:
            try:
                metadata[field] = str(getattr(self, field))
            except AttributeError:
                pass

        for field in normal_fields:
            try:
                metadata[field] = getattr(self, field)
            except AttributeError:
                pass

        try:
            metadata["authors"] = list(
                map(lambda author: author.username, self.authors)
            )
        except AttributeError:
            pass
        try:
            metadata["series"] = list(map(lambda series: series.name, self.series))
        except AttributeError:
            pass
        try:
            metadata["chapter_titles"] = list(
                map(lambda chapter: chapter.title, self.chapters)
            )
        except AttributeError:
            pass

        return metadata

    def get_comments(self, maximum: Optional[int] = None) -> list[Comment]:
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

        if not self.loaded:
            raise UnloadedException(
                "Work isn't loaded. Have you tried calling Work.reload()?"
            )

        url = f"https://archiveofourown.org/works/{self.id}?page=%d&show_comments=true&view_adult=true&view_full_work=true"
        soup = self.request(url % 1)

        pages = 0
        div = soup.find("div", {"id": "comments_placeholder"})
        ol = div.find("ol", {"class": "pagination actions"})
        if ol is None:
            pages = 1
        else:
            for li in ol.findAll("li"):
                if li.getText().isdigit():
                    pages = int(li.getText())

        comments = []
        for page in range(pages):
            if page != 0:
                soup = self.request(url % (page + 1))
            ol = soup.find("ol", {"class": "thread"})
            for li in ol.findAll("li", {"role": "article"}, recursive=False):
                if maximum is not None and len(comments) >= maximum:
                    return comments
                id_ = int(li.attrs["id"][8:])

                header = li.find("h4", {"class": ("heading", "byline")})
                if header is None or header.a is None:
                    author = None
                else:
                    author = User(str(header.a.text), self._session, False)

                if li.blockquote is not None:
                    text = li.blockquote.getText()
                else:
                    text = ""

                comment = Comment(id_, self, session=self._session, load=False)
                setattr(comment, "authenticity_token", self.authenticity_token)
                setattr(comment, "author", author)
                setattr(comment, "text", text)
                comment._thread = None
                comments.append(comment)
        return comments

    @threadable.threadable
    def subscribe(self) -> None:
        """Subscribes to this work.
        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

        if self._session is None or not self._session.is_authed:
            raise AuthException(
                "You can only subscribe to a work using an authenticated session"
            )

        utils.subscribe(self, "Work", self._session)

    @threadable.threadable
    def unsubscribe(self) -> None:
        """Unubscribes from this user.
        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

        if not self.is_subscribed:
            raise Exception("You are not subscribed to this work")
        if self._session is None or not self._session.is_authed:
            raise AuthException(
                "You can only unsubscribe from a work using an authenticated session"
            )

        utils.subscribe(self, "Work", self._session, True, self._sub_id)

    @cached_property
    def text(self) -> str:
        """This work's full text."""

        text = ""
        for chapter in self.chapters:
            text += chapter.text
            text += "\n"
        return text

    @cached_property
    def authenticity_token(self) -> Optional[str]:
        """Token used to take actions that involve this work"""

        if not self.loaded:
            return None

        token = self._soup.find("meta", {"name": "csrf-token"})
        return token["content"]

    @cached_property
    def is_subscribed(self) -> bool:
        """True if you're subscribed to this work."""

        if self._session is None or not self._session.is_authed:
            raise AuthException(
                "You can only get a user ID using an authenticated session"
            )

        ul = self._soup.find("ul", {"class": "work navigation actions"})
        input_ = ul.find("li", {"class": "subscribe"}).find(
            "input", {"name": "commit", "value": "Unsubscribe"}
        )
        return input_ is not None

    @cached_property
    def _sub_id(self) -> Optional[int]:
        """Returns the subscription ID. Used for unsubscribing"""

        if self._session is None or not self._session.is_authed:
            raise AuthException(
                "You can only get a user ID using an authenticated session"
            )

        ul = self._soup.find("ul", {"class": "work navigation actions"})
        id_ = ul.find("li", {"class": "subscribe"}).form.attrs["action"].split("/")[-1]
        return int(id_)

    @threadable.threadable
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

        if self._session is None:
            raise AuthException("Invalid session")
        return utils.kudos(self, self._session)

    @threadable.threadable
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

        if not self.loaded:
            raise UnloadedException(
                "Work isn't loaded. Have you tried calling Work.reload()?"
            )

        if self._session is None:
            raise AuthException("Invalid session")

        return utils.comment(
            self, comment_text, self._session, True, email=email, name=name, pseud=pseud
        )

    @threadable.threadable
    def bookmark(
        self,
        notes: Optional[str] = "",
        tags: Optional[list[str]] = None,
        collections: Optional[list[str]] = None,
        private: Optional[bool] = False,
        recommend: Optional[bool] = False,
        pseud: Optional[str] = None,
    ) -> None:
        """Bookmarks this work.

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

        if not self.loaded:
            raise UnloadedException(
                "Work isn't loaded. Have you tried calling Work.reload()?"
            )

        if self._session is None:
            raise AuthException("Invalid session")

        utils.bookmark(
            self, self._session, notes, tags, collections, private, recommend, pseud
        )

    @threadable.threadable
    def delete_bookmark(self) -> None:
        """Removes a bookmark from this work.

        This function is threadable

        Raises:
            utils.UnloadedError: Work isn't loaded
            utils.AuthError: Invalid session
        """

        if not self.loaded:
            raise UnloadedException(
                "Work isn't loaded. Have you tried calling Work.reload()?"
            )

        if self._session is None:
            raise AuthException("Invalid session")

        if self._bookmarkid is None:
            raise BookmarkException("You don't have a bookmark here")

        utils.delete_bookmark(self._bookmarkid, self._session, self.authenticity_token)

    @threadable.threadable
    def collect(self, collections) -> None:
        """Invites/collects this work to a collection or collections.

        This function is threadable

        Args:
            collections (list): What collections to add this work to. Defaults to None.

        Raises:
            utils.UnloadedError: Work isn't loaded
            utils.AuthError: Invalid session
        """

        if not self.loaded:
            raise UnloadedException(
                "Work isn't loaded. Have you tried calling Work.reload()?"
            )

        if self._session is None:
            raise AuthException("Invalid session")

        utils.collect(self, self._session, collections)

    @cached_property
    def _bookmarkid(self) -> Optional[int]:
        """
        Return the id of the specific bookmark.

        :return:
        """
        form_div = self._soup.find("div", {"id": "bookmark-form"})
        if form_div is None:
            return None
        if form_div.form is None:
            return None
        if "action" in form_div.form.attrs and form_div.form["action"].startswith(
            "/bookmarks"
        ):
            text = form_div.form["action"].split("/")[-1]
            if text.isdigit():
                return int(text)
            return None
        return None

    @property
    def loaded(self) -> bool:
        """Returns True if this work has been loaded."""
        return self._soup is not None

    @property
    def oneshot(self) -> bool:
        """Returns True if this work has only one chapter."""
        return self.nchapters == 1

    @cached_property
    def series(self) -> list["SeriesAPI"]:
        """Returns the series this work belongs to"""

        from ao3.series import Series

        dd = self._soup.find("dd", {"class": "series"})
        if dd is None:
            return []

        s = []
        for span in dd.find_all("span", {"class": "position"}):
            seriesid = int(span.a.attrs["href"].split("/")[-1])
            seriesname = span.a.getText()
            series = Series(seriesid, self._session, False)
            setattr(series, "name", seriesname)
            s.append(series)
        return s

    @cached_property
    def authors(self) -> list["User"]:
        """Returns the list of the work's author

        Returns:
            list: list of authors
        """

        if self._soup is None:
            raise UnloadedException(f"Cannot read authors - work is not loaded.")

        from ao3.users import User

        authors = self._soup.find_all("h3", {"class": "byline heading"})
        if len(authors) == 0:
            return []
        formatted_authors = authors[0].text.replace("\n", "").split(", ")
        author_list = []
        if authors is not None:
            for author in formatted_authors:
                user = User(author, load=False)
                author_list.append(user)

        return author_list

    @cached_property
    def nchapters(self) -> int:
        """Returns the number of chapters of this work

        Returns:
            int: number of chapters
        """
        if self.restricted and not self.session.is_authed:
            raise AuthException(
                "Restricted work - you need to be logged in to get a chapter count."
            )

        chapters = self._soup.find("dd", {"class": "chapters"})
        if chapters is not None:
            return int(self.str_format(chapters.string.split("/")[0]))
        return 0

    @cached_property
    def expected_chapters(self) -> Optional[int]:
        """Returns the number of expected chapters for this work, or None if
        the author hasn't provided an expected number

        Returns:
            int: number of chapters
        """
        chapters = self._soup.find("dd", {"class": "chapters"})
        if chapters is not None:
            n = self.str_format(chapters.string.split("/")[-1])
            if n.isdigit():
                return int(n)
        return None

    @property
    def status(self) -> Union[Literal["Completed"], Literal["Work in Progress"]]:
        """Returns the status of this work

        Returns:
            str: work status
        """
        if self.nchapters == self.expected_chapters:
            return "Completed"
        else:
            return "Work in Progress"

    @cached_property
    def hits(self) -> int:
        """Returns the number of hits this work has

        Returns:
            int: number of hits
        """

        hits = self._soup.find("dd", {"class": "hits"})
        if hits is not None:
            return int(self.str_format(hits.string))
        return 0

    @cached_property
    def kudos(self) -> int:
        """Returns the number of kudos this work has

        Returns:
            int: number of kudos
        """

        kudos = self._soup.find("dd", {"class": "kudos"})
        if kudos is not None:
            return int(self.str_format(kudos.string))
        return 0

    @cached_property
    def comments(self) -> int:
        """Returns the number of comments this work has

        Returns:
            int: number of comments
        """

        comments = self._soup.find("dd", {"class": "comments"})
        if comments is not None:
            return int(self.str_format(comments.string))
        return 0

    @cached_property
    def restricted(self) -> bool:
        """Whether this is a restricted work or not

        Returns:
            bool: True if work is restricted
        """
        if self._main_page_rep is not None and urls_match(
            self._main_page_rep.url,
            "https://archiveofourown.org/users/login?restricted=true",
        ):
            return True

        return self._soup.find("img", {"title": "Restricted"}) is not None

    @cached_property
    def words(self) -> int:
        """Returns the this work's word count

        Returns:
            int: number of words
        """

        words = self._soup.find("dd", {"class": "words"})
        if words is not None:
            return int(self.str_format(words.string))
        return 0

    @cached_property
    def language(self) -> str:
        """Returns this work's language

        Returns:
            str: Language
        """

        language = self._soup.find("dd", {"class": "language"})
        if language is not None:
            return language.string.strip()
        else:
            return "Unknown"

    @cached_property
    def bookmarks(self) -> int:
        """Returns the number of bookmarks this work has

        Returns:
            int: number of bookmarks
        """

        bookmarks = self._soup.find("dd", {"class": "bookmarks"})
        if bookmarks is not None:
            return int(self.str_format(bookmarks.string))
        return 0

    @cached_property
    def title(self) -> str:
        """Returns the title of this work

        Returns:
            str: work title
        """

        title = self._soup.find("div", {"class": "preface group"})
        if title is not None:
            return str(title.h2.text.strip())
        return ""

    @cached_property
    def date_published(self) -> datetime.date:
        """Returns the date this work was published.

        Returns:
            datetime.date: publish date
        """

        dp = self._soup.find("dd", {"class": "published"}).string
        return datetime(*list(map(int, dp.split("-"))))

    @cached_property
    def date_edited(self) -> datetime.date:
        """Returns the date this work was last edited.

        Returns:
            datetime.datetime: edit date
        """

        download = self._soup.find("li", {"class": "download"})

        if download is not None and download.ul is not None:
            timestamp = int(download.ul.a["href"].split("=")[-1])
            return datetime.fromtimestamp(timestamp)

        return self.date_published

    @cached_property
    def date_updated(self) -> datetime.date:
        """Returns the date this work was last updated.

        Returns:
            datetime.datetime: update date
        """
        update = self._soup.find("dd", {"class": "status"})
        if update is not None:
            split = update.string.split("-")
            return datetime(*list(map(int, split)))
        return self.date_published

    @cached_property
    def tags(self) -> list[str]:
        """Returns all the work's tags.

        Returns:
            list: List of tags
        """

        html = self._soup.find("dd", {"class": "freeform tags"})
        tags = []
        if html is not None:
            for tag in html.find_all("li"):
                tags.append(tag.a.string)
        return tags

    @cached_property
    def characters(self) -> list[str]:
        """Returns all the work's characters

        Returns:
            list: List of characters
        """

        html = self._soup.find("dd", {"class": "character tags"})
        characters = []
        if html is not None:
            for character in html.find_all("li"):
                characters.append(character.a.string)
        return characters

    @cached_property
    def relationships(self) -> list[str]:
        """Returns all the work's relationships

        Returns:
            list: List of relationships
        """

        html = self._soup.find("dd", {"class": "relationship tags"})
        relationships = []
        if html is not None:
            for relationship in html.find_all("li"):
                relationships.append(relationship.a.string)
        return relationships

    @cached_property
    def fandoms(self) -> list[str]:
        """Returns all the work's fandoms

        Returns:
            list: List of fandoms
        """

        html = self._soup.find("dd", {"class": "fandom tags"})
        fandoms = []
        if html is not None:
            for fandom in html.find_all("li"):
                fandoms.append(fandom.a.string)
        return fandoms

    @cached_property
    def categories(self) -> list[str]:
        """Returns all the work's categories

        Returns:
            list: List of categories
        """

        html = self._soup.find("dd", {"class": "category tags"})
        categories = []
        if html is not None:
            for category in html.find_all("li"):
                categories.append(category.a.string)
        return categories

    @cached_property
    def warnings(self) -> list[str]:
        """Returns all the work's warnings

        Returns:
            list: List of warnings
        """

        html = self._soup.find("dd", {"class": "warning tags"})
        warnings = []
        if html is not None:
            for warning in html.find_all("li"):
                warnings.append(warning.a.string)
        return warnings

    @cached_property
    def rating(self) -> Optional[str]:
        """Returns this work's rating

        Returns:
            (None, str): Rating
        """

        html = self._soup.find("dd", {"class": "rating tags"})
        if html is not None:
            rating = html.a.string
            return rating
        return None

    @cached_property
    def summary(self) -> str:
        """Returns this work's summary.

        Returns:
            str: Summary
        """

        div = self._soup.find("div", {"class": "preface group"})
        if div is None:
            return ""
        html = div.find("blockquote", {"class": "userstuff"})
        if html is None:
            return ""
        return str(BeautifulSoup.getText(html))

    @cached_property
    def start_notes(self) -> str:
        """Text from this work's start notes."""
        notes = self._soup.find("div", {"class": "notes module"})
        if notes is None:
            return ""
        text = ""
        for p in notes.findAll("p"):
            text += p.getText().strip() + "\n"
        return text

    @cached_property
    def end_notes(self) -> str:
        """Text from this work's end notes"""
        notes = self._soup.find("div", {"id": "work_endnotes"})
        if notes is None:
            return ""
        text = ""
        for p in notes.findAll("p"):
            text += p.getText() + "\n"
        return text

    @cached_property
    def url(self) -> str:
        """Returns the URL to this work

        Returns:
            str: work URL
        """

        return f"https://archiveofourown.org/works/{self.id}"

    @cached_property
    def complete(self) -> bool:
        """
        Return True if the work is complete

        Retuns:
            bool: True if a work is complete
        """

        chapterStatus = self._soup.find("dd", {"class": "chapters"}).string.split("/")
        return chapterStatus[0] == chapterStatus[1]

    @cached_property
    def collections(self) -> list[str]:
        """Returns all the collections the work belongs to

        Returns:
            list: List of collections
        """

        html = self._soup.find("dd", {"class": "collections"})
        collections = []
        if html is not None:
            for collection in html.find_all("a"):
                collections.append(collection.get_text())
        return collections
