
"""
Tests for the series class.

"""

import time

import pytest

import ao3.utils
import errors
from ao3.series import Series

from .. import get_authed_session


class TestSeriesExists:
    """
    Tests a series that exists and we should be able to access.
    """
    def test_series_exists_unauthed_session(self) -> None:
        """
        We're going to load story 1.

        This should fail with a 404 - as the story does, in fact, not exist anymore.
        :return:
        """
        time.sleep(0.5)

        target_url = "https://archiveofourown.org/series/4676659"

        from ao3.session import GuestSession

        test_series = Series(
            seriesid=4676659,
            session=GuestSession(),
            load=True
        )

        assert test_series is not None
        assert test_series == test_series

        assert repr(test_series) == '<Series [Lower Decks Continues]>'

    def test_cannot_subscribe_unauthed_session(self) -> None:
        """
        Attempt, and fail, to subscribe to the series as a guest.

        :return:
        """
        time.sleep(0.5)

        from ao3.session import GuestSession

        test_series = Series(
            seriesid=4676659,
            session=GuestSession(),
            load=True
        )

        with pytest.raises(errors.AuthException):
            test_series.subscribe()

        with pytest.raises(errors.AuthException):
            test_series.unsubscribe()

    def test_check_is_subscribed_authed_session(self) -> None:
        """
        Checks to see if we can tell if we're subscribed in an authed session.

        :return:
        """
        test_session = get_authed_session()

        test_series = Series(
            seriesid=4676659,
            session=test_session,
            load=True
        )

        subbed_property = test_series.is_subscribed






    def test_can_subscribe_authed_session(self) -> None:
        """
        Attempt, and fail, to subscribe to the series as a guest.

        :return:
        """
        time.sleep(0.5)

        test_session = get_authed_session()
        test_session.refresh_auth_token()

        test_series = Series(
            seriesid=4676659,
            session=test_session,
            load=True
        )

        test_series.subscribe()

        time.sleep(0.5)

        test_series.unsubscribe()



