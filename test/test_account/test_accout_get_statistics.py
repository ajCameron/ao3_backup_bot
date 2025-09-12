
"""
Tests te get_subsriptions method under accounts.
"""

from ao3.models import SubscriptionItem, WorkSubscriptionItem, SeriesSubscriptionItem, UserSubscriptionItem

from ao3.session.api import Ao3SessionUnPooled
from ao3.account import Account
from ao3.users import User


from test import get_secrets_dict


class TestAccountGetStatistics:
    """
    Breaking down the get_history method, to check that we're parsing the soup properly.

    Or it could just be taking a really long time.
    Note - for these tests to work you need to prepare your account with subscriptions to works, user, series.
    """
    def test_get_statistics(self) -> None:
        """
        Tests the get_statistics method runs without error.

        :return:
        """
        secrets_dict = get_secrets_dict()

        test_session = Ao3SessionUnPooled(
            username=secrets_dict["username"], password=secrets_dict["password"]
        )

        assert test_session.logged_in is True

        test_account = Account(session=test_session)

        test_account_subs = test_account.get_statistics()

        # Sa
        assert test_account_subs == dict()
