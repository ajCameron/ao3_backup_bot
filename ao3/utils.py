import os
import pickle
import re

from typing import Optional, Union

import requests.models
from datetime import datetime
from bs4 import BeautifulSoup

from ao3.requester import requester

from ao3.common import url_join
from ao3.api.comment_session_work_api import WorkAPI
from ao3.errors import (
    UnloadedException,
    UnexpectedResponseException,
    InvalidIdException,
    AuthException,
    DuplicateCommentException,
    PseudException,
    HTTPException,
    BookmarkException,
    CollectException,
)

from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


_FANDOMS: Optional[list[str]] = None
_LANGUAGE: Optional[list[str]] = None

AO3_AUTH_ERROR_URL = "https://archiveofourown.org/auth_error"


class Constraint:
    """Represents a bounding box of a value."""

    def __init__(
        self, lowerbound: Optional[int] = 0, upperbound: Optional[int] = None
    ) -> None:
        """Creates a new Constraint object

        Args:
            lowerbound (int, optional): Constraint lowerbound. Defaults to 0.
            upperbound (int, optional): Constraint upperbound. Defaults to None.
        """

        self._lb = lowerbound
        self._ub = upperbound

    @property
    def string(self) -> str:
        """Returns the string representation of this constraint.

        Then can be used in query.

        Returns:
            str: string representation
        """

        if self._lb == 0:
            return f"<{self._ub}"
        elif self._ub is None:
            return f">{self._lb}"
        elif self._ub == self._lb:
            return str(self._lb)
        else:
            return f"{self._lb}-{self._ub}"

    def __str__(self) -> str:
        """
        String rep of the constraint.

        :return:
        """
        return self.string


def word_count(text: str) -> int:
    """
    Returns the "true" word count of the string.

    :param text:
    :return:
    """
    return len(tuple(filter(lambda w: w != "", re.split(" |\n|\t", text))))


def set_rqtw(value: int) -> None:
    """Sets the requests per time window parameter for the AO3 requester."""
    requester.setRQTW(value)


def set_timew(value: int) -> None:
    """Sets the time window parameter for the AO3 requester."""
    requester.setTimeW(value)


def limit_requests(limit: bool = True) -> None:
    """Toggles request limiting."""
    if limit:
        requester.setRQTW(12)
    else:
        requester.setRQTW(-1)


def load_fandoms() -> None:
    """Loads fandoms into memory

    Raises:
        FileNotFoundError: No resource was found

    :return None: All changes to internal cache
    """

    global _FANDOMS

    fandom_path = os.path.join(os.path.dirname(__file__), "resources", "fandoms")
    if not os.path.isdir(fandom_path):
        raise FileNotFoundError(
            "No fandom resources have been downloaded. Try AO3.extra.download()"
        )
    files = os.listdir(fandom_path)
    _FANDOMS = []
    for file in files:
        with open(os.path.join(fandom_path, file), "rb") as f:
            _FANDOMS += pickle.load(f)


def load_languages() -> None:
    """Loads languages into memory

    Raises:
        FileNotFoundError: No resource was found
    """

    global _LANGUAGES

    language_path = os.path.join(os.path.dirname(__file__), "resources", "languages")
    if not os.path.isdir(language_path):
        raise FileNotFoundError(
            "No language resources have been downloaded. Try AO3.extra.download()"
        )
    files = os.listdir(language_path)
    _LANGUAGES = []
    for file in files:
        with open(os.path.join(language_path, file), "rb") as f:
            _LANGUAGES += pickle.load(f)


def get_languages() -> list[str]:
    """Returns all available languages."""
    return _LANGUAGES[:]


def search_fandom(fandom_string: str) -> list[str]:
    """Searches for a fandom that matches the given string

    Args:
        fandom_string (str): query string

    Raises:
        UnloadedError: load_fandoms() wasn't called
        UnloadedError: No resources were downloaded

    Returns:
        list: All results matching 'fandom_string'
    """

    if _FANDOMS is None:
        raise UnloadedException("Did you forget to call AO3.utils.load_fandoms()?")

    if not _FANDOMS:
        raise UnloadedException(
            "Did you forget to download the required resources with AO3.extra.download()?"
        )
    results = []
    assert isinstance(_FANDOMS, list), "type hacking"
    for fandom in _FANDOMS:
        if fandom_string.lower() in fandom.lower():
            results.append(fandom)
    return results


def workid_from_url(url: str) -> Optional[int]:
    """Get the workid from an archiveofourown.org website url.

    Args:
        url (str): Work URL

    Returns:
        int: Work ID
    """
    split_url = url.split("/")
    try:
        index = split_url.index("works")
    except ValueError:
        return
    if len(split_url) >= index + 1:
        workid = split_url[index + 1].split("?")[0]
        if workid.isdigit():
            return int(workid)
    return


def comment(
    commentable: Optional[Union[WorkAPI, "Chapter"]],
    comment_text: str,
    session: "Session",
    fullwork: bool = False,
    commentid: Union[str, int] = None,
    email: str = "",
    name: str = "",
    pseud: Optional[str] = None,
):
    """Leaves a comment on a specific work

    Args:
        commentable (Work/Chapter): Chapter/Work object
        comment_text (str): Comment text (must have between 1 and 10000 characters)
        fullwork (bool): Should be True if the work has only one chapter or if the comment is to be posted on the full work.
        session (AO3.Session/AO3.GuestSession): Session object to request with.
        commentid (str/int): If specified, the comment is posted as a reply to this comment. Defaults to None.
        email (str): Email to post with. Only used if sess is None. Defaults to "".
        name (str): Name that will appear on the comment. Only used if sess is None. Defaults to "".
        pseud (str, optional): What pseud to add the comment under. Defaults to default pseud.

    Raises:
        utils.InvalidIdError: Invalid ID
        utils.UnexpectedResponseError: Unknown error
        utils.PseudError: Couldn't find a valid pseudonym to post under
        utils.DuplicateCommentError: The comment you're trying to post was already posted
        ValueError: Invalid name/email

    Returns:
        requests.models.Response: Response object
    """

    if commentable.authenticity_token is not None:
        at = commentable.authenticity_token
    else:
        at = session.authenticity_token
    headers = {
        "x-requested-with": "XMLHttpRequest",
        "x-newrelic-id": "VQcCWV9RGwIJVFFRAw==",
        "x-csrf-token": at,
    }

    data = {}
    if fullwork:
        data["work_id"] = str(commentable.id)
    else:
        data["chapter_id"] = str(commentable.id)
    if commentid is not None:
        data["comment_id"] = commentid

    if session.is_authed:
        if fullwork:
            referer = f"https://archiveofourown.org/works/{commentable.id}"
        else:
            referer = f"https://archiveofourown.org/chapters/{commentable.id}"

        pseud_id = get_pseud_id(commentable, session, pseud)
        if pseud_id is None:
            raise PseudException("Couldn't find your pseud's id")

        data.update(
            {
                "authenticity_token": at,
                "comment[pseud_id]": pseud_id,
                "comment[comment_content]": comment_text,
            }
        )

    else:
        if email == "" or name == "":
            raise ValueError("You need to specify both an email and a name!")

        data.update(
            {
                "authenticity_token": at,
                "comment[email]": email,
                "comment[name]": name,
                "comment[comment_content]": comment_text,
            }
        )

    response = session.post(
        f"https://archiveofourown.org/comments.js", headers=headers, data=data
    )
    if response.status_code == 429:
        raise HTTPException(
            "We are being rate-limited. Try again in a while or reduce the number of requests"
        )
    if response.status_code == 404:
        if len(response.content) > 0:
            return response
        else:
            raise InvalidIdException(
                f"Invalid {'work ID' if fullwork else 'chapter ID'}"
            )

    if response.status_code == 422:
        json = response.json()
        if "errors" in json:
            if "auth_error" in json["errors"]:
                raise AuthException(
                    "Invalid authentication token. Try calling session.refresh_auth_token()"
                )
        raise UnexpectedResponseException(f"Unexpected json received:\n{str(json)}")
    elif response.status_code == 200:
        raise DuplicateCommentException("You have already left this comment here")

    raise UnexpectedResponseException(
        f"Unexpected HTTP status code received ({response.status_code})"
    )


def delete_comment(comment: "Comment", session: "Session") -> None:
    """Deletes the specified comment

    Args:
        comment (AO3.Comment): Comment object
        session (AO3.Session): Session object

    Raises:
        PermissionError: You don't have permission to delete the comment
        utils.AuthError: Invalid auth token
        utils.UnexpectedResponseError: Unknown error
    """

    if session is None or not session.is_authed:
        raise PermissionError("You don't have permission to do this")

    if comment.authenticity_token is not None:
        at = comment.authenticity_token
    else:
        at = session.authenticity_token

    data = {"authenticity_token": at, "_method": "delete"}

    req = session.post(f"https://archiveofourown.org/comments/{comment.id}", data=data)
    if req.status_code == 429:
        raise HTTPException(
            "We are being rate-limited. Try again in a while or reduce the number of requests"
        )
    else:
        soup = BeautifulSoup(req.content, "lxml")
        if "auth error" in soup.title.getText().lower():
            raise AuthException(
                "Invalid authentication token. Try calling session.refresh_auth_token()"
            )
        else:
            error = soup.find("div", {"id": "main"}).getText()
            if "you don't have permission" in error.lower():
                raise PermissionError("You don't have permission to do this")


def kudos(work: WorkAPI, session: "Session") -> bool:
    """Leave a 'kudos' for a specific work.

    Args:
        work (Work): Work object

    Raises:
        utils.UnexpectedResponseError: Unexpected response received
        utils.InvalidIdError: Invalid ID (work doesn't exist)
        utils.AuthError: Invalid authenticity token

    Returns:
        bool: True if successful, False if you already left kudos there
    """

    if work.authenticity_token is not None:
        at = work.authenticity_token
    else:
        at = session.authenticity_token
    data = {
        "authenticity_token": at,
        "kudo[commentable_id]": work.id,
        "kudo[commentable_type]": WorkAPI,
    }
    headers = {
        "x-csrf-token": work.authenticity_token,
        "x-requested-with": "XMLHttpRequest",
        "referer": f"https://archiveofourown.org/work/{work.id}",
    }
    response = session.post(
        "https://archiveofourown.org/kudos.js", headers=headers, data=data
    )
    if response.status_code == 429:
        raise HTTPException(
            "We are being rate-limited. Try again in a while or reduce the number of requests"
        )

    if response.status_code == 201:
        return True  # Success
    elif response.status_code == 422:
        json = response.json()
        if "errors" in json:
            if "auth_error" in json["errors"]:
                raise AuthException(
                    "Invalid authentication token. Try calling session.refresh_auth_token()"
                )
            elif "user_id" in json["errors"] or "ip_address" in json["errors"]:
                return False  # User has already left kudos
            elif "no_commentable" in json["errors"]:
                raise InvalidIdException("Invalid ID")
        raise UnexpectedResponseException(f"Unexpected json received:\n" + str(json))
    else:
        raise UnexpectedResponseException(
            f"Unexpected HTTP status code received ({response.status_code})"
        )


def subscribe(
    subscribable: Union[WorkAPI, "Series", "User"],
    worktype: str,
    session: "Session",
    unsubscribe: Optional[bool] = False,
    subid: Optional[Union[str, int]] = None,
):
    """Subscribes to a work/series/user.

    Be careful, you can subscribe to a work multiple times.
    For some reason.

    Args:
        subscribable (Work/Series/User): AO3 object
        worktype (str): Type of the work (Series/Work/User)
        session (AO3.Session): Session object
        unsubscribe (bool, optional): Unsubscribe instead of subscribing. Defaults to False.
        subid (str/int, optional): Subscription ID, used when unsubscribing. Defaults to None.

    Raises:
        AuthError: Invalid auth token
        AuthError: Invalid session
        InvalidIdError: Invalid ID / worktype
        InvalidIdError: Invalid subid
    """

    if session is None:
        session = subscribable.session
    if session is None or not session.is_authed:
        raise AuthException("Invalid session")

    if subscribable.authenticity_token is not None:
        at = subscribable.authenticity_token
    else:
        at = session.authenticity_token

    data = {
        "authenticity_token": at,
        "subscription[subscribable_id]": subscribable.id,
        "subscription[subscribable_type]": worktype.capitalize(),
    }

    url = f"https://archiveofourown.org/users/{session.username}/subscriptions"
    if unsubscribe:
        if subid is None:
            raise InvalidIdException("When unsubscribing, subid cannot be None")
        url += f"/{subid}"
        data["_method"] = "delete"
    req = session.session.post(url, data=data, allow_redirects=False)
    if unsubscribe:
        return req
    if req.status_code == 302:
        if req.headers["Location"] == AO3_AUTH_ERROR_URL:
            raise AuthException(
                "Invalid authentication token. Try calling session.refresh_auth_token()"
            )
    else:
        raise InvalidIdException(f"Invalid ID / worktype")


def bookmark(
    bookmarkable: Union[WorkAPI, "Series"],
    session: Optional["Session"] = None,
    notes: Optional[str] = "",
    tags: Optional[list[str]] = None,
    collections: Optional[list[str]] = None,
    private: Optional[bool] = False,
    recommend: Optional[bool] = False,
    pseud: Optional[str] = None,
) -> None:
    """Adds a bookmark to a work/series. Be careful, you can bookmark a work multiple times

    Args:
        bookmarkable (Work/Series): AO3 object
        session (AO3.Session): Session object
        notes (str, optional): Bookmark notes. Defaults to "".
        tags (list, optional): What tags to add. Defaults to None.
        collections (list, optional): What collections to add this bookmark to. Defaults to None.
        private (bool, optional): Whether this bookmark should be private. Defaults to False.
        recommend (bool, optional): Whether to recommend this bookmark. Defaults to False.
        pseud (str, optional): What pseud to add the bookmark under. Defaults to default pseud.
    """

    if session is None:
        session = bookmarkable.session
    if session == None or not session.is_authed:
        raise AuthException("Invalid session")

    if bookmarkable.authenticity_token is not None:
        at = bookmarkable.authenticity_token
    else:
        at = session.authenticity_token

    if tags is None:
        tags = []
    if collections is None:
        collections = []

    pseud_id = get_pseud_id(bookmarkable, session, pseud)
    if pseud_id is None:
        raise PseudException("Couldn't find your pseud's id")

    data = {
        "authenticity_token": at,
        "bookmark[pseud_id]": pseud_id,
        "bookmark[tag_string]": ",".join(tags),
        "bookmark[collection_names]": ",".join(collections),
        "bookmark[private]": int(private),
        "bookmark[rec]": int(recommend),
        "commit": "Create",
    }

    if notes != "":
        data["bookmark[bookmarker_notes]"] = notes

    url = url_join(bookmarkable.url, "bookmarks")
    req = session.session.post(url, data=data, allow_redirects=False)
    handle_bookmark_errors(req)


def delete_bookmark(
    bookmarkid: Optional[Union[WorkAPI, "Series"]],
    session: Optional["Session"],
    auth_token: Optional[str] = None,
) -> None:
    """Remove a bookmark from the work/series.

    Args:
        bookmarkid (Work/Series): AO3 object
        session (AO3.Session): Session object
        auth_token (str, optional): Authenticity token. Defaults to None.
    """
    if session == None or not session.is_authed:
        raise AuthException("Invalid session")

    data = {
        "authenticity_token": (
            session.authenticity_token if auth_token is None else auth_token
        ),
        "_method": "delete",
    }

    url = f"https://archiveofourown.org/bookmarks/{bookmarkid}"
    req = session.session.post(url, data=data, allow_redirects=False)
    handle_bookmark_errors(req)


def handle_bookmark_errors(response: requests.models.Response) -> None:
    """
    Generate ao3 errors based on the request response.

    :param response:
    :return:
    """
    if response.status_code == 302:
        if response.headers["Location"] == AO3_AUTH_ERROR_URL:
            raise AuthException(
                "Invalid authentication token. Try calling session.refresh_auth_token()"
            )
    else:
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "lxml")
            error_div = soup.find("div", {"id": "error", "class": "error"})
            if error_div is None:
                raise UnexpectedResponseException("An unknown error occurred")

            errors = [item.getText() for item in error_div.findAll("li")]
            if len(errors) == 0:
                raise BookmarkException("An unknown error occurred")
            raise BookmarkException("Error(s) creating bookmark:" + " ".join(errors))

        raise UnexpectedResponseException(
            f"Unexpected HTTP status code received ({response.status_code})"
        )


def get_pseud_id(
    ao3object: Union[WorkAPI, "Chapter", "User"],
    session: Optional["Session"] = None,
    specified_pseud: Optional[str] = None,
) -> Optional[str]:
    """
    Get the pseud corresponding to the object.

    :param ao3object:
    :param session:
    :param specified_pseud:

    :return:
    """
    if session is None:
        session = ao3object.session
    if session is None or not session.is_authed:
        raise AuthException("Invalid session")

    soup = session.request(ao3object.url)
    pseud = soup.find("input", {"name": re.compile(".+\\[pseud_id\\]")})
    if pseud is None:
        pseud = soup.find("select", {"name": re.compile(".+\\[pseud_id\\]")})
        if pseud is None:
            return None
        pseud_id = None
        if specified_pseud:
            for option in pseud.findAll("option"):
                if option.string == specified_pseud:
                    pseud_id = option.attrs["value"]
                    break
        else:
            for option in pseud.findAll("option"):
                if (
                    "selected" in option.attrs
                    and option.attrs["selected"] == "selected"
                ):
                    pseud_id = option.attrs["value"]
                    break
    else:
        pseud_id = pseud.attrs["value"]
    return pseud_id


def collect(
    collectable: WorkAPI, session: "Session", collections: Optional[list["Collection"]]
) -> None:
    """Invites a work to a collection. Be careful, you can collect a work multiple times

    Args:
        collectable (Work): A thing which can be collected - maybe a work?
        session (AO3.Session): Session object
        collections (list, optional): What collections to add this work to. Defaults to None.
    """

    if session is None:
        session = collectable.session
    if session == None or not session.is_authed:
        raise AuthException("Invalid session")

    if collectable.authenticity_token is not None:
        at = collectable.authenticity_token
    else:
        at = session.authenticity_token

    if collections is None:
        collections = []

    data = {
        "authenticity_token": at,
        "collection_names": ",".join(collections),
        "commit": "Add",
    }

    url = url_join(collectable.url, "collection_items")
    req = session.session.post(url, data=data, allow_redirects=True)

    if req.status_code == 302:
        if req.headers["Location"] == AO3_AUTH_ERROR_URL:
            raise AuthException(
                "Invalid authentication token. Try calling session.refresh_auth_token()"
            )
    elif req.status_code == 200:
        soup = BeautifulSoup(req.content, "lxml")
        notice_div = soup.find("div", {"class": "notice"})

        error_div = soup.find("div", {"class": "error"})

        if error_div is None and notice_div is None:
            raise UnexpectedResponseException("An unknown error occurred")

        if error_div is not None:
            errors = [item.getText() for item in error_div.findAll("ul")]

            if len(errors) == 0:
                raise CollectException("An unknown error occurred")

            raise CollectException(
                "We couldn't add your submission to the following collection(s): "
                + " ".join(errors)
            )
    else:
        raise UnexpectedResponseException(
            f"Unexpected HTTP status code received ({req.status_code})"
        )


def normalize_url(url: str) -> str:
    """
    Bring a URL into standard form.

    :param url:
    :return:
    """
    parsed = urlparse(url)

    # Normalize netloc (case-insensitive, remove default ports)
    netloc = parsed.hostname.lower() if parsed.hostname else ""
    if parsed.port and (
        (parsed.scheme == "http" and parsed.port != 80)
        or (parsed.scheme == "https" and parsed.port != 443)
    ):
        netloc += f":{parsed.port}"

    # Normalize path: ensure no trailing slashes if unnecessary
    path = parsed.path or "/"

    # Normalize query string (sorted)
    query = urlencode(sorted(parse_qsl(parsed.query)))

    return urlunparse(
        (
            parsed.scheme,
            netloc,
            path,
            "",  # params
            query,
            "",  # fragment
        )
    )


def urls_match(a: str, b: str) -> bool:
    """
    Check that two urls are the same.

    :param a:
    :param b:
    :return:
    """
    return normalize_url(a) == normalize_url(b)


_DATE_PATTERNS = ("%d %b %Y", "%d %b %Y %H:%M", "%Y-%m-%d")  # expand if AO3 varies


def parse_int(text: str) -> Optional[int]:
    m = re.search(r"(\d[\d,]*)", text or "")
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def parse_date(text: str) -> Optional[datetime]:
    text = (text or "").strip()
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None