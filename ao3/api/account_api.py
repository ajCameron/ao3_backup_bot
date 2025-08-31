
"""
Contains the API for the account class - which
"""

from functools import cached_property

import abc


class AccountAPI(abc.ABC):
    """
    API for the account class - representing your account on AO3.
    """
    session: "SessionAPI"

    def __init__(self, session: "SessionAPI") -> None:
        """
        Attach a session to this Account.

        The session has to be authenticated to do anything useful.
        :param session:
        """
        self.session = session

    @abc.abstractmethod
    def clear_cache(self) -> None:
        """
        Clear the internal properties cache

        :return:
        """
        raise NotImplementedError("Not supported for this Session type.")
