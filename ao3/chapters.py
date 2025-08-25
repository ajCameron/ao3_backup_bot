"""
Represents an individual chapter inside a larger work.
"""

from functools import cached_property

import requests

from typing import Optional

import bs4

from ao3 import errors
from ao3 import threadable, utils
from ao3.comments import Comment
from ao3.api.object_api import BaseObjectAPI
from ao3.api.comment_session_work_api import WorkAPI
from ao3.users import User


class Chapter(BaseObjectAPI):
    """
    AO3 chapter object
    """

    _session: Optional["Session"]
    _work: WorkAPI

    def __init__(
        self,
        chapterid: Optional[int],
        work: WorkAPI,
        session: "Session" = None,
        load: bool = True,
    ) -> None:
        """
        Initialise the chapter.

        :param chapterid: Chapter int id on AO3.
        :param work: The Work the chapter belongs to .
        :param session: Session object used for querying the archive.
        :param load: Preload the chapter?
        """
        self._session = session
        self._work = work
        self.id = chapterid
        self._soup = None
        if load:
            self.reload()

    def __repr__(self) -> str:
        """
        str rep of the class.

        :return:
        """
        if self.id is None:
            return f"Chapter [ONESHOT] from [{self.work}]"
        try:
            return f"<Chapter [{self.title} ({self.number})] from [{self.work}]>"
        except Exception as e:
            return f"<Chapter [{self.id}] from [{self.work}] - [{e}]>"

    def __eq__(self, other: "Chapter") -> bool:
        """
        Check equality between this chapter and another.

        :param other:
        :return:
        """
        return isinstance(other, self.__class__) and other.id == self.id

    def set_session(self, session: "Session") -> None:
        """Sets the session used to make requests for this chapter

        Args:
            session (AO3.Session/AO3.GuestSession): session object
        """

        self._session = session

    @threadable.threadable
    def reload(self) -> None:
        """
        Loads information about this chapter.

        This function is threadable.
        """
        from .works import Work

        for attr in self.__class__.__dict__:
            if isinstance(getattr(self.__class__, attr), cached_property):
                if attr in self.__dict__:
                    delattr(self, attr)

        if self.work is None:
            soup = self.request(
                f"https://archiveofourown.org/chapters/{self.id}?view_adult=true"
            )
            workid = soup.find("li", {"class": "chapter entire"})
            if workid is None:
                raise errors.InvalidIdException("Cannot find work")
            self._work = Work(utils.workid_from_url(workid.a["href"]))
        else:
            self.work.reload()

        for chapter in self.work.chapters:
            if chapter == self:
                self._soup = chapter._soup

    @threadable.threadable
    def comment(
        self,
        comment_text: str,
        email: str = "",
        name: str = "",
        pseud: Optional[str] = None,
    ):
        """Leaves a comment on this chapter.

        This function is threadable.

        Args:
            comment_text (str): Comment text
            email (str): Email to associated with the comment
            name (str): Name to associate with the comment
            pseud (str, optional): What pseud to add the comment under. Defaults to default pseud.

        Raises:
            utils.UnloadedError: Couldn't load chapters
            utils.AuthError: Invalid session

        Returns:
            requests.models.Response: Response object
        """

        if self.id is None:
            return self._work.comment(comment_text, email, name, pseud)

        if not self.loaded:
            raise errors.UnloadedException(
                "Chapter isn't loaded. Have you tried calling Chapter.reload()?"
            )

        if self._session is None:
            raise errors.AuthException("Invalid session")

        if self.id is not None:
            return utils.comment(
                self,
                comment_text,
                self._session,
                False,
                email=email,
                name=name,
                pseud=pseud,
            )

    def get_comments(self, maximum: Optional[int] = None) -> list[Comment]:
        """
        Returns a list of all threads of comments in the chapter.

        This operation can take a very long time.
        Because of that, it is recommended that you set a maximum number of comments.
        Duration: ~ (0.13 * n_comments) seconds or 2.9 seconds per comment page

        Args:
            maximum (int, optional): Maximum number of comments to be returned. None -> No maximum

        Raises:
            ValueError: Invalid chapter number
            IndexError: Invalid chapter number
            utils.UnloadedError: Chapter isn't loaded

        Returns:
            list: List of comments
        """

        if self.id is None:
            return self._work.get_comments(maximum=maximum)

        if not self.loaded:
            raise errors.UnloadedException(
                "Chapter isn't loaded. Have you tried calling Chapter.reload()?"
            )

        url = f"https://archiveofourown.org/chapters/{self.id}?page=%d&show_comments=true&view_adult=true"
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
                if header is None:
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

    def get_images(self) -> tuple[tuple[str, int], ...]:
        """Gets all images from this work

        Raises:
            utils.UnloadedError: Raises this error if the chapter isn't loaded

        Returns:
            tuple: Pairs of image urls and the paragraph number
        """

        div = self._soup.find("div", {"class": "userstuff"})
        images = []
        line = 0
        for p in div.findAll("p"):
            line += 1
            for img in p.findAll("img"):
                if "src" in img.attrs:
                    images.append((img.attrs["src"], line))
        return tuple(images)

    @property
    def loaded(self) -> bool:
        """Returns True if this chapter has been loaded"""
        return self._soup is not None

    @property
    def authenticity_token(self) -> str:
        """Token used to take actions that involve this work."""
        return self.work.authenticity_token

    @property
    def work(self) -> WorkAPI:
        """Work this chapter is a part of."""
        return self._work

    @cached_property
    def text(self) -> str:
        """This chapter's text"""
        text = ""
        if self.id is not None:
            div = self._soup.find("div", {"role": "article"})
        else:
            div = self._soup
        for p in div.findAll(("p", "center")):
            text += p.getText().replace("\n", "") + "\n"
            if isinstance(p.next_sibling, bs4.element.NavigableString):
                text += str(p.next_sibling)
        return text

    @cached_property
    def title(self) -> str:
        """This chapter's title,"""
        if self.id is None:
            return self.work.title
        preface_group = self._soup.find(
            "div", {"class": ("chapter", "preface", "group")}
        )
        if preface_group is None:
            return str(self.number)
        title = preface_group.find("h3", {"class": "title"})
        if title is None:
            return str(self.number)
        return tuple(title.strings)[-1].strip()[2:]

    @cached_property
    def number(self) -> int:
        """This chapter's number."""
        if self.id is None:
            return 1
        return int(self._soup["id"].split("-")[-1])

    @cached_property
    def words(self) -> int:
        """Number of words from this chapter"""
        return utils.word_count(self.text)

    @cached_property
    def summary(self) -> str:
        """Text from this chapter's summary."""
        notes = self._soup.find("div", {"id": "summary"})
        if notes is None:
            return ""
        text = ""
        for p in notes.findAll("p"):
            text += p.getText() + "\n"
        return text

    @cached_property
    def start_notes(self) -> str:
        """Text from this chapter's start notes"""
        notes = self._soup.find("div", {"id": "notes"})
        if notes is None:
            return ""
        text = ""
        for p in notes.findAll("p"):
            text += p.getText().strip() + "\n"
        return text

    @cached_property
    def end_notes(self) -> str:
        """Text from this chapter's end notes"""
        notes = self._soup.find("div", {"id": f"chapter_{self.number}_endnotes"})
        if notes is None:
            return ""
        text = ""
        for p in notes.findAll("p"):
            text += p.getText() + "\n"
        return text

    @cached_property
    def url(self) -> str:
        """Returns the URL to this chapter

        Returns:
            str: chapter URL
        """

        return f"https://archiveofourown.org/works/{self._work.id}/chapters/{self.id}"
