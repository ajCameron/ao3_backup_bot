from __future__ import annotations

import dataclasses
from typing import Optional


@dataclasses.dataclass(frozen=True)
class FetchResult:
    """
    What happened when we tried to load the chapter off the archive.
    """

    ao3_id: int  # The id we're trying to load
    authed: bool  # Did we try and access this work while authed?

    outcome: str  # The classified result of the call
    http_status_code: int  # What status code accessing the page
    html: str  # Html return from the page, for later analysis
    final_url: str  # URL after any redirects
    err: Optional[str]  # If there was an error during the call
    user: Optional[str]  # Which user we have used to try the login

    sess: Optional[object]  # The session we used

    meta: dict  # Anything else we can think of
