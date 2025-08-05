"""
There's an annoying circular import between work and session.

So splitting the session api out so we can import and ref it in both places.
"""


class SessionAPI: ...
