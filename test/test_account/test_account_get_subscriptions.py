
"""
Tests te get_subsriptions method under accounts.
"""

from ao3.models import SubscriptionItem, WorkSubscriptionItem, SeriesSubscriptionItem, UserSubscriptionItem

from ao3.session.api import Ao3SessionUnPooled
from ao3.account import Account
from ao3.users import User


from test import get_secrets_dict


class TestAccountGetSubscriptionsUnthreaded:
    """
    Breaking down the get_history method, to check that we're parsing the soup properly.

    Or it could just be taking a really long time.
    Note - for these tests to work you need to prepare your account with subscriptions to works, user, series.
    """

    use_threading = False

    def test_get_subscriptions_direct_call(self) -> None:
        """
        Just call get_history and see if it works.

        :return:
        """
        secrets_dict = get_secrets_dict()

        test_session = Ao3SessionUnPooled(
            username=secrets_dict["username"], password=secrets_dict["password"]
        )

        assert test_session.logged_in is True

        test_account = Account(session=test_session)

        test_account_subs = test_account.get_subscriptions(use_threading=self.use_threading)

        assert test_account_subs is not None

    def test_account_get_subscriptions(self) -> None:
        """
        Just call get_history and see if it works.

        :return:
        """
        secrets_dict = get_secrets_dict()

        test_session = Ao3SessionUnPooled(
            username=secrets_dict["username"], password=secrets_dict["password"]
        )

        assert test_session.logged_in is True

        test_account = Account(session=test_session)

        test_account_subs = test_account.get_subscriptions(use_threading=self.use_threading)

        assert test_account_subs is not None

        assert len(test_account_subs) > 0

        for sub in test_account_subs:

            # Generic tests
            assert isinstance(sub, SubscriptionItem)

            # Work tests
            if isinstance(sub, WorkSubscriptionItem):

                # As this is how ao3 ids work
                assert isinstance(sub.id, int) and sub.id >= 0
                assert isinstance(sub.title, str) and sub.title

                # Every work should have an author
                assert sub.authors and isinstance(sub.authors, list)
                for sub_author in sub.authors:
                    assert isinstance(sub_author, str)
                assert sub.href == f"/works/{sub.id}"
                assert sub.user is None
                assert sub.user_url is None

            # User tests
            elif isinstance(sub, UserSubscriptionItem):

                # There's not a good way to pull an id out of this
                # But you do have pseudids... hopefully
                assert sub.id == 0
                assert isinstance(sub.title, str) and sub.title

                assert not hasattr(sub, "authors")

                assert sub.href == f"/users/{sub.title}"
                assert isinstance(sub.user, str) and sub.user
                assert isinstance(sub.user_url, str) and sub.user_url.startswith("/users")

            elif isinstance(sub, SeriesSubscriptionItem):

                # Todo: I think ao3 may use a unified interger incrementing id system of some kind...
                assert isinstance(sub.id, int) and sub.id
                assert isinstance(sub.title, str)
                assert isinstance(sub.authors, list)
                for sub_author in sub.authors:
                    assert isinstance(sub_author, str) and sub_author
                assert isinstance(sub.href, str) and sub.href.startswith("/series/")

                assert not hasattr(sub, "user"), "Doesn't seem to make sense here"
                assert not hasattr(sub, "user_url"), "Doesn't seem to make sense here"
                assert not hasattr(sub, "user_pseud"), "Doesn't seem to make sense here"

            else:
                raise NotImplementedError(f"Unexpected type - {type(sub) = }")

    def test_get_user_subscriptions(self) -> None:
        """
        Tests the account get_user_subscriptions method - which should return UserSubscription objects.

        :return:
        """
        secrets_dict = get_secrets_dict()

        test_session = Ao3SessionUnPooled(
            username=secrets_dict["username"], password=secrets_dict["password"]
        )

        assert test_session.logged_in is True

        test_account = Account(session=test_session)

        test_user_subs = test_account.get_user_subscriptions(use_threading=self.use_threading)

        assert test_user_subs is not None

        for user_sub in test_user_subs:
            assert isinstance(user_sub, UserSubscriptionItem)

    def test_get_work_subscriptions(self) -> None:
        """
        Tests the account get_user_subscriptions method - which should return UserSubscription objects.

        :return:
        """
        secrets_dict = get_secrets_dict()

        test_session = Ao3SessionUnPooled(
            username=secrets_dict["username"], password=secrets_dict["password"]
        )

        assert test_session.logged_in is True

        test_account = Account(session=test_session)

        test_work_subs = test_account.get_work_subscriptions(use_threading=self.use_threading)

        assert test_work_subs is not None

        for user_sub in test_work_subs:
            assert isinstance(user_sub, WorkSubscriptionItem)

    def test_get_series_subscriptions(self) -> None:
        """
        Tests the account get_user_subscriptions method - which should return UserSubscription objects.

        :return:
        """
        secrets_dict = get_secrets_dict()

        test_session = Ao3SessionUnPooled(
            username=secrets_dict["username"], password=secrets_dict["password"]
        )

        assert test_session.logged_in is True

        test_account = Account(session=test_session)

        test_series_subs = test_account.get_series_subscriptions(use_threading=self.use_threading)

        assert test_series_subs is not None

        for user_sub in test_series_subs:
            assert isinstance(user_sub, SeriesSubscriptionItem)


class TestAccountGetSubscriptionsThreaded(TestAccountGetSubscriptionsUnthreaded):
    """
    Breaking down the get_history method, to check that we're parsing the soup properly.

    Or it could just be taking a really long time.
    Note - for these tests to work you need to prepare your account with subscriptions to works, user, series.
    """

    use_threading = True