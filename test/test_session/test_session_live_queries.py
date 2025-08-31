
"""
Debugging the auth flow from session.
"""
import datetime
from typing import Optional, Union

import pytest
from bs4 import BeautifulSoup


import warnings
import requests

from ao3.errors import LoginException, AuthException
from ao3.session.api import Ao3Session, Ao3SessionUnPooled
from ao3.requester import Requester
from ao3.works import Work


from test import get_secrets_dict


class TestSessionLoginFollowedByCalls:
    """
    We're going to login to a session and then we're going to run all methods that touch the site.

    Ideally, we want a small number of big, bulky method that does basically everywhere.
    We don't want to thrash Ao3. They might not like it.
    """

    _session: None

    def test_authed_unpooled_session_get_work_subscriptions(self) -> None:
        """
        For some reason I'm not sure we're properly logging in.

        :return:
        """
        secrets_dict = get_secrets_dict()

        test_session = Ao3SessionUnPooled(
            username=secrets_dict["username"], password=secrets_dict["password"]
        )

        assert test_session.logged_in is True

        assert test_session.get_subscriptions_url(1) \
               == \
               "https://archiveofourown.org/users/thomaswpaine/subscriptions?page=1"

        assert test_session.post_login_title == 'thomaswpaine | Archive of Our Own'

        subbed_series = test_session.get_series_subscriptions(use_threading=False)
        assert isinstance(subbed_series, list), "Expecting a list back, and didn't get it."

        subbed_works = test_session.get_work_subscriptions(use_threading=False)
        assert isinstance(subbed_works, list), "Expecting a list back, and didn't get it."

        full_history = test_session.get_history()
        assert isinstance(full_history, list)
        for work_tuple in full_history:
            assert isinstance(work_tuple, list)
            assert len(work_tuple) == 3
            assert isinstance(work_tuple[0],Work)
            assert isinstance(work_tuple[1], int)
            assert isinstance(work_tuple[2], datetime.datetime)

        bookmark_count = test_session.bookmarks
        assert isinstance(bookmark_count, int)
        assert bookmark_count > 0

        all_bookmarks = test_session.get_bookmarks(use_threading=False)
        assert isinstance(all_bookmarks, list)
        for book_mark in all_bookmarks:
            assert isinstance(book_mark, Work)



