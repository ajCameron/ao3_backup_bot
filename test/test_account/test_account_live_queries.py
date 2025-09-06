
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
from ao3.account import Account
from ao3.models import HistoryItem


from test import get_secrets_dict


class TestSessionLoginFollowedByAccountCallsUnthreaded:
    """
    We're going to login to a session and then we're going to run all methods that touch the site.

    Ideally, we want a small number of big, bulky method that does basically everywhere.
    We don't want to thrash Ao3. They might not like it.

    ... we might want to thrash them a bit.

    Using unthreaded methods.
    """

    _session: None

    use_threading: bool = False

    def test_authed_unpooled_account_all_methods_unthreaded(self) -> None:
        """
        Log in and then use all the session methods.

        The aim is to trip bandwidth limits (and to check the functions kinda work together).
        :return:
        """
        secrets_dict = get_secrets_dict()

        test_session = Ao3SessionUnPooled(
            username=secrets_dict["username"], password=secrets_dict["password"]
        )

        assert test_session.logged_in is True

        test_account = Account(session=test_session)

        assert test_account.get_subscriptions_url(1) \
               == \
               "https://archiveofourown.org/users/thomaswpaine/subscriptions?page=1"

        assert test_session.post_login_title == 'thomaswpaine | Archive of Our Own'

        subbed_series = test_account.get_series_subscriptions(use_threading=self.use_threading)
        assert isinstance(subbed_series, list), "Expecting a list back, and didn't get it."

        subbed_works = test_account.get_work_subscriptions(use_threading=self.use_threading)
        assert isinstance(subbed_works, list), "Expecting a list back, and didn't get it."

        full_history = test_account.get_history()
        assert isinstance(full_history, list)
        for work_tuple in full_history:
            assert isinstance(work_tuple, HistoryItem)

            assert isinstance(work_tuple.work_id, int)
            assert isinstance(work_tuple.work_title, str)
            assert isinstance(work_tuple.last_read_at, datetime.datetime)
            assert isinstance(work_tuple.authors, list)
            for author in work_tuple.authors:
                assert isinstance(author, str)
            assert isinstance(work_tuple.chapter_count, int)
            assert isinstance(work_tuple.words, int)
            assert isinstance(work_tuple.visited_date, datetime.datetime)
            assert isinstance(work_tuple.visited_num, int)

        bookmark_count = test_account.bookmarks
        assert isinstance(bookmark_count, int)
        assert bookmark_count > 0

        all_bookmarks = test_account.get_bookmarks(use_threading=self.use_threading)
        assert isinstance(all_bookmarks, list)
        for book_mark in all_bookmarks:
            assert isinstance(book_mark, Work)


class TestSessionLoginFollowedByAccountCallsThreaded(TestSessionLoginFollowedByAccountCallsUnthreaded):
    """
    We're going to login to a session and then we're going to run all methods that touch the site.

    Ideally, we want a small number of big, bulky method that does basically everywhere.
    We don't want to thrash Ao3. They might not like it.

    ... we might want to thrash them a bit.

    Using threaded methods.
    """
    use_threading = True


class TestAccountGetHistory:
    """
    Tests, in detail, the get_history method on the Account class.
    """


    def test_account_get_history(self) -> None:
        """
        Tests the get_history account function.

        :return:
        """
        secrets_dict = get_secrets_dict()

        test_session = Ao3SessionUnPooled(
            username=secrets_dict["username"], password=secrets_dict["password"]
        )

        assert test_session.logged_in is True

        test_account = Account(session=test_session)

        full_history = test_account.get_history()

        assert isinstance(full_history, list)
        for work_tuple in full_history:
            assert isinstance(work_tuple, HistoryItem)

            assert isinstance(work_tuple.work_id, int)
            assert isinstance(work_tuple.work_title, str)
            assert isinstance(work_tuple.last_read_at, datetime.datetime)
            assert isinstance(work_tuple.authors, list)
            for author in work_tuple.authors:
                assert isinstance(author, str)
            assert isinstance(work_tuple.chapter_count, int)
            assert isinstance(work_tuple.words, int)
            assert isinstance(work_tuple.visited_date, datetime.datetime)
            assert isinstance(work_tuple.visited_num, int)