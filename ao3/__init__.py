"""

Programmatic tools to access and download from ao3.

Original fork from https://github.com/wendytg/ao3_api
Alterations are my own fault.

Public API for the ao3 package.

Typical usage:

    import ao3

    session = ao3.Session()
    work = ao3.Work(123456)
    work.fetch()  # if your Work model lazily loads

    # Helpers live under ao3.utils
    wid = ao3.utils.workid_from_url("https://archiveofourown.org/works/123456")

Only the names exported here are considered stable.
Everything else should be treated as internal and may change without notice.
"""

from __future__ import annotations


from ao3 import utils
from ao3.works import Work
from ao3.chapters import Chapter
from ao3.session import Ao3Session, GuestAo3Session
from ao3.comments import Comment


# Version
from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("ao3")
except PackageNotFoundError:
    # When running from a source checkout (editable install not yet built)
    __version__ = "0.0.0.dev0"

# Public classes
from ao3.session import Ao3Session  # Auth, cookies, CSRF, logged-in actions
from ao3.works import Work  # Core work model (metadata, chapters, download)
from ao3.chapters import Chapter
from ao3.comments import Comment
from ao3.users import User
from ao3.series import Series

# Public helpers live in a namespaced module so we don't flood the top level.
# (Users will do `ao3.utils.workid_from_url(...)` etc.)
from ao3 import utils

# Public search surface: keep it namespaced for now to avoid top-level clutter.
# Users can call `ao3.search.search_works(...)` (or whatever functions you expose).
from ao3 import search

# Typed, user-facing exceptions
from ao3.errors import (
    LoginException,
    DownloadException,
NetworkException
)

# Optional: expose a canonical list of supported download file types if your
# Work model defines one. We fall back gracefully if it doesn’t exist.
try:
    # Convention: a module-constant or class-constant on Work
    FILETYPES = getattr(Work, "DOWNLOAD_FILETYPES", None) or getattr(
        Work, "FILETYPES", None
    )
except Exception:  # pragma: no cover
    FILETYPES = None

__all__ = [
    # Version
    "__version__",
    # Core models
    "Ao3Session",
    "Work",
    "Chapter",
    "Comment",
    "User",
    "Series",
    # Namespaced helpers/modules
    "utils",
    "search",
    # Exceptions
    "LoginException",
    "DownloadException",
    "NetworkException",
    # Optional constants
    "FILETYPES",
]
