"""
Central location for errors the program might throw.
"""

from typing import Optional


class AO3Exception(Exception):
    """
    Base class for all exceptions this API can throw.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message)
        self.errors = errors if errors is not None else []


class LoginException(AO3Exception):
    """
    Attempting to login to the archive has failed.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message=message, errors=errors)


class UnloadedException(AO3Exception):
    """
    Resource needs to be loaded before it can be accessed.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message=message, errors=errors)


class NetworkException(AO3Exception):
    """
    Something seems to have gone wrong on a network level.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message=message, errors=errors)


class UnexpectedResponseException(NetworkException):
    """
    There was an unexpected HTTP response from the archive.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message=message, errors=errors)


class HTTPException(NetworkException):
    """
    Accessing a webpage seems to have gone wrong.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message=message, errors=errors)


class RateLimitException(HTTPException):
    """
    Error might be resolved by backing off.

    Do that.
    """

    pass


class InvalidIdException(AO3Exception):
    """
    An invalid id has been passed to the constructor.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message=message, errors=errors)


class WorkNotFoundException(InvalidIdException):
    """
    The id looked valid, but an id was not found.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message=message, errors=errors)


class DownloadException(AO3Exception):
    """
    An attempt to download a work has failed.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message=message, errors=errors)


class AuthException(AO3Exception):
    """
    An authentication error has occurred.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message=message, errors=errors)


class DuplicateCommentException(AO3Exception):
    """
    Attempting to make a duplicate comment - this is not allowed.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message=message, errors=errors)


class PseudException(AO3Exception):
    """
    Pseud = Pseudonym - which is used to post under.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message=message, errors=errors)


class BookmarkException(AO3Exception):
    """
    Something had gone wrong - with a bookmark.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message=message, errors=errors)


class CollectException(AO3Exception):
    """
    Attempting to collect a work has failed.
    """

    def __init__(self, message: str, errors: Optional[list[Exception]] = None) -> None:
        """
        Startup the exception.

        :param message:
        :param errors:
        """
        super().__init__(message=message, errors=errors)
