"""
Class to represent an ao3 comment.

These can be part of a comment tree - and can either be attatched to a work entire or a specific chaptr.
"""

from functools import cached_property

from typing import Optional, Union, Iterator


import bs4
import requests.models
from bs4 import BeautifulSoup

from ao3 import threadable, utils
from ao3.users import User

from api.comment_session_work_api import CommentAPI, WorkAPI, Ao3SessionAPI
from ao3.api.object_api import BaseObjectAPI


class Comment(CommentAPI, BaseObjectAPI):
    """
    AO3 comment object
    """

    def __init__(
        self,
        comment_id: Union[str, int],
        parent: Optional[Union["WorkAPI", "Chapter"]] = None,
        parent_comment: Optional["Comment"] = None,
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

        super().__init__(
            comment_id=comment_id,
            parent=parent,
            parent_comment=parent_comment,
            session=session,
        )

        if load:
            self.reload()

    def __repr__(self) -> str:
        """
        String rep of the class.

        :return:
        """
        return f"<Comment [{self.id}] on [{self.parent}]>"

    @property
    def _soup(self) -> Optional[BeautifulSoup]:
        """
        Return the soup containing this comment.

        :return:
        """
        if self.__soup is None:
            if self.parent_comment is None:
                return None
            return self.parent_comment._soup
        return self.__soup

    @property
    def first_parent_comment(self) -> "CommentAPI":
        """
        Return the first parent of this comment tree (which might be this comment).

        :return:
        """
        if self.parent_comment is None:
            return self
        else:
            return self.parent_comment.first_parent_comment

    @property
    def fullwork(self) -> Optional[bool]:
        """
        Check to see if this comment is on the full work.

        :return:
        """
        from .works import Work

        if self.parent is None:
            return None
        return isinstance(self.parent, Work)

    @cached_property
    def author(self) -> Optional["User"]:
        """Comment author."""
        li = self._soup.find("li", {"id": f"comment_{self.id}"})
        header = li.find("h4", {"class": ("heading", "byline")})
        if header is None:
            author = None
        else:
            author = User(str(header.a.text), self._session, False)
        return author

    @cached_property
    def text(self) -> str:
        """Comment text."""
        li = self._soup.find("li", {"id": f"comment_{self.id}"})
        if li.blockquote is not None:
            text = li.blockquote.getText()
        else:
            text = ""
        return text

    def get_thread(self) -> list["CommentAPI"]:
        """Returns all the replies to this comment, and all subsequent replies recursively.

        Also loads any parent comments this comment might have.

        Poorly named - could mean the thread of execution.

        Raises:
            utils.InvalidIdError: The specified comment_id was invalid

        Returns:
            list: Thread
        """

        if self._thread is not None:
            return self._thread
        else:
            if self._soup is None:
                self.reload()

            nav = self._soup.find("ul", {"id": f"navigation_for_comment_{self.id}"})
            for li in nav.findAll("li"):
                if li.getText() == "\nParent Thread\n":
                    id_ = int(li.a["href"].split("/")[-1])
                    parent = Comment(id_, session=self._session)
                    for comment in parent.get_thread_iterator():
                        if comment.id == self.id:
                            index = comment.parent_comment._thread.index(comment)
                            comment.parent_comment._thread.pop(index)
                            comment.parent_comment._thread.insert(index, self)
                            self._thread = comment._thread
                            self.parent_comment = comment.parent_comment
                            del comment
                            return self._thread

            thread = self._soup.find("ol", {"class": "thread"})
            if thread is None:
                self._thread = []
                return self._thread

            self._get_thread(None, thread)

            if self._thread is None:
                self._thread = []
            return self._thread

    def _get_thread(
        self,
        parent: Optional["Comment"],
        soup: Optional[Union[bs4.PageElement, bs4.Tag, bs4.NavigableString]],
    ) -> None:
        """
        Setup the thread this comment is part of.

        :param parent:
        :param soup:
        :return:
        """
        comments = soup.findAll("li", recursive=False)
        l = [self] if parent is None else []
        for comment in comments:
            if "role" in comment.attrs:
                id_ = int(comment.attrs["id"][8:])
                c = Comment(id_, self.parent, session=self._session, load=False)
                c.authenticity_token = self.authenticity_token
                c._thread = []
                if parent is not None:
                    c.parent_comment = parent
                    if comment.blockquote is not None:
                        text = comment.blockquote.getText()
                    else:
                        text = ""
                    if comment.a is not None:
                        author = User(comment.a.getText(), load=False)
                    else:
                        author = None
                    setattr(c, "text", text)
                    setattr(c, "author", author)
                    l.append(c)
                else:
                    c.parent_comment = self
                    if comment.blockquote is not None:
                        text = comment.blockquote.getText()
                    else:
                        text = ""
                    if comment.a is not None:
                        author = User(comment.a.getText(), load=False)
                    else:
                        author = None
                    setattr(l[0], "text", text)
                    setattr(l[0], "author", author)
            else:
                self._get_thread(l[-1], comment.ol)
        if parent is not None:
            parent._thread = l

    def get_thread_iterator(self) -> Iterator["CommentAPI"]:
        """Returns a generator that allows you to iterate through the entire thread

        Returns:
            generator: The generator object
        """

        return comment_thread_iterator(self)

    @threadable.threadable
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

        if self.parent is None:
            raise ValueError("self.parent cannot be 'None'")
        return utils.comment(
            self.parent,
            comment_text,
            self._session,
            self.fullwork,
            self.id,
            email,
            name,
        )

    @threadable.threadable
    def reload(self) -> None:
        """Loads all comment properties.

        This function is threadable.

        :return None: All changes are to the internal cache
        """

        for attr in self.__class__.__dict__:
            if isinstance(getattr(self.__class__, attr), cached_property):
                if attr in self.__dict__:
                    delattr(self, attr)

        req = self.get(f"https://archiveofourown.org/comments/{self.id}")
        self.__soup = BeautifulSoup(req.content, features="lxml")

        token = self.__soup.find("meta", {"name": "csrf-token"})
        self.authenticity_token = token["content"]

        self._thread = None

        li = self._soup.find("li", {"id": f"comment_{self.id}"})

        reply_link = li.find("li", {"id": f"add_comment_reply_link_{self.id}"})

        if self.parent is None:
            if reply_link is not None:
                fields = [
                    field.split("=")
                    for field in reply_link.a["href"].split("?")[-1].split("&")
                ]
                for key, value in fields:
                    if key == "chapter_id":
                        self.parent = int(value)
                        break
        self.parent_comment = None

    @threadable.threadable
    def delete(self) -> None:
        """Deletes this comment.
        This function is threadable.

        Raises:
            PermissionError: You don't have permission to delete the comment
            utils.AuthError: Invalid auth token
            utils.UnexpectedResponseError: Unknown error
        """

        utils.delete_comment(self, self._session)


def comment_thread_iterator(comment: CommentAPI) -> Iterator[CommentAPI]:
    """
    Iterate over the thread a given comment is in.

    :param comment:
    :return:
    """
    if comment.get_thread() is None or len(comment.get_thread()) == 0:
        yield comment
    else:
        for c in comment.get_thread():
            yield c
            for sub in comment_thread_iterator(c):
                if c != sub:
                    yield sub
