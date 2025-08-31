"""
Debugging the auth flow from session.
"""

import pytest


from ao3.errors import AuthException
from ao3.session.api import Ao3Session, Ao3SessionUnPooled


from .. import get_secrets_dict


class TestSessionLogin:
    """
    We've got some problems logging in - debugging.
    """

    _session: None

    def test_authed_session_entire_init(self) -> None:
        """
        Tests we can init a session.

        :return:
        """
        secrets_dict = get_secrets_dict()

        test_session = Ao3Session(
            username=secrets_dict["username"], password=secrets_dict["password"]
        )

        assert test_session.logged_in is True

    def test_authed_session_entire_init_bad_password(self) -> None:
        """
        Tests we can init a session.

        :return:
        """
        secrets_dict = get_secrets_dict()

        with pytest.raises(AuthException):

            Ao3Session(
                username=secrets_dict["username"], password="test_password"
            )