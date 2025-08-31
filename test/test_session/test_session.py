
"""
Debugging the auth flow from session.
"""

from typing import Optional, Union

import pytest
from bs4 import BeautifulSoup


import warnings
import requests

from ao3.errors import LoginException, AuthException
from ao3.session.api import Ao3Session, Ao3SessionUnPooled
from ao3.session.ao3session import PrototypeSession
from ao3.requester import Requester


from test import get_secrets_dict


class TestSessionLogin:
    """
    We've got some problems logging in - debugging.
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


    # def test_basic_flow_valid_username_and_valid_password_direct_session(self) -> None:
    #     """
    #     Tests the basic authentication flow.
    #
    #     :return:
    #     """
    #
    #     secrets_dict = get_secrets_dict()
    #
    #     session = requests.Session()
    #
    #     login_page_url = "https://archiveofourown.org/users/login"
    #
    #     soup = self.request(login_page_url, force_session=session)
    #
    #     assert soup.status_code == 200
    #
    #     assert soup.find("input")["name"] == 'authenticity_token'
    #
    #     authenticity_token = soup.find("input")["value"]
    #
    #     assert len(authenticity_token) == 86
    #
    #     payload = {
    #         "user[login]": secrets_dict["username"],
    #         "user[password]": secrets_dict["password"],
    #         "authenticity_token": authenticity_token,
    #     }
    #
    #     login_post_resp = self.post(
    #         "https://archiveofourown.org/users/login",
    #         params=payload,
    #         allow_redirects=False, force_session=session
    #     )
    #
    #     if login_post_resp.status_code == 302:
    #         login_post_resp = self.post(
    #             "https://archiveofourown.org/users/login",
    #             params=payload,
    #             allow_redirects=True, force_session=session
    #         )
    #
    #     assert login_post_resp.status_code == 200
    #     assert len(login_post_resp.history) == 1
    #     assert login_post_resp.history[0].status_code == 302
    #
    #     content_type = login_post_resp.headers.get("content-type", "")
    #     charset = "utf-8"  # sensible default
    #
    #     if "charset=" in content_type:
    #         charset = content_type.split("charset=")[-1].split(";")[0].strip()
    #
    #     # Decode using the detected charset
    #
    #     raw_html = login_post_resp.content.decode(charset, errors="replace")
    #
    #     assert len(raw_html) > 500
    #
    #     soup = BeautifulSoup(raw_html, "html.parser")
    #
    #     # --- Extract the title ---
    #     title = soup.title.string if soup.title else None
    #
    #     assert title == 'thomaswpaine | Archive of Our Own'

    def test_basic_flow_valid_username_and_valid_password_requester(self) -> None:
        """
        Tests the basic authentication flow.

        :return:
        """

        secrets_dict = get_secrets_dict()

        session = requests.Session()
        test_requester = Requester()
        test_requester.attach_session(session)

        login_page_url = "https://archiveofourown.org/users/login"

        soup = self.request(login_page_url, force_session=test_requester)

        assert soup.status_code == 200

        assert soup.find("input")["name"] == 'authenticity_token'

        authenticity_token = soup.find("input")["value"]

        assert len(authenticity_token) == 86

        payload = {
            "user[login]": secrets_dict["username"],
            "user[password]": secrets_dict["password"],
            "authenticity_token": authenticity_token,
        }

        login_post_resp = self.post(
            "https://archiveofourown.org/users/login",
            params=payload,
            allow_redirects=False, force_session=session
        )

        if login_post_resp.status_code == 302:
            login_post_resp = self.post(
                "https://archiveofourown.org/users/login",
                params=payload,
                allow_redirects=True, force_session=session
            )

        assert login_post_resp.status_code == 200
        assert len(login_post_resp.history) == 1
        assert login_post_resp.history[0].status_code == 302

        content_type = login_post_resp.headers.get("content-type", "")
        charset = "utf-8"  # sensible default

        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].split(";")[0].strip()

        # Decode using the detected charset

        raw_html = login_post_resp.content.decode(charset, errors="replace")

        assert len(raw_html) > 500

        soup = BeautifulSoup(raw_html, "html.parser")

        # --- Extract the title ---
        title = soup.title.string if soup.title else None

        assert title == 'thomaswpaine | Archive of Our Own'

    # def test_basic_flow_valid_username_and_bad_password_direct_session(self) -> None:
    #     """
    #     Tests the basic authentication flow.
    #
    #     :return:
    #     """
    #
    #     secrets_dict = get_secrets_dict()
    #
    #     session = requests.Session()
    #
    #     login_page_url = "https://archiveofourown.org/users/login"
    #
    #     soup = self.request(login_page_url, force_session=session)
    #
    #     assert soup.find("input")["name"] == 'authenticity_token'
    #
    #     authenticity_token = soup.find("input")["value"]
    #
    #     payload = {
    #         "user[login]": secrets_dict["username"],
    #         "user[password]": "NOT THE RIGHT PASSWORD",
    #         "authenticity_token": authenticity_token,
    #     }
    #
    #     login_post_resp = self.post(
    #         "https://archiveofourown.org/users/login",
    #         params=payload,
    #         allow_redirects=False, force_session=session
    #     )
    #
    #     if login_post_resp.status_code == 302:
    #         login_post_resp = self.post(
    #             "https://archiveofourown.org/users/login",
    #             params=payload,
    #             allow_redirects=True, force_session=session
    #         )
    #
    #     assert login_post_resp.status_code == 200
    #     assert len(login_post_resp.history) == 1
    #     assert login_post_resp.history[0].status_code == 302
    #
    #     content_type = login_post_resp.headers.get("content-type", "")
    #     charset = "utf-8"  # sensible default
    #
    #     if "charset=" in content_type:
    #         charset = content_type.split("charset=")[-1].split(";")[0].strip()
    #
    #     # Decode using the detected charset
    #
    #     raw_html = login_post_resp.content.decode(charset, errors="replace")
    #
    #     assert len(raw_html) > 500
    #
    #     soup = BeautifulSoup(raw_html, "html.parser")
    #
    #     # --- Extract the title ---
    #     title = soup.title.string if soup.title else None
    #
    #     assert title == "Auth Error | Archive of Our Own"

    # def test_basic_flow_valid_username_and_password_direct_session(self) -> None:
    #     """
    #     Tests the basic authentication flow.
    #
    #     :return:
    #     """
    #
    #     secrets_dict = get_secrets_dict()
    #
    #     session = requests.Session()
    #
    #     login_page_url = "https://archiveofourown.org/users/login"
    #
    #     soup = self.request(login_page_url, force_session=session)
    #
    #     assert soup.find("input")["name"] == 'authenticity_token'
    #
    #     authenticity_token = soup.find("input")["value"]
    #
    #     payload = {
    #         "user[login]": secrets_dict["username"],
    #         "user[password]": secrets_dict["password"],
    #         "authenticity_token": authenticity_token,
    #     }
    #     login_post = self.post(
    #         "https://archiveofourown.org/users/login",
    #         params=payload,
    #         allow_redirects=False, force_session=session
    #     )
    #
    #     if login_post.status_code == 302:
    #         login_post = self.post(
    #             "https://archiveofourown.org/users/login",
    #             params=payload,
    #             allow_redirects=True, force_session=session
    #         )
    #
    #     assert login_post.status_code == 200
    #     assert len(login_post.history) == 1
    #     assert login_post.history[0].status_code == 302

    def request(self,
                url: str,
                proxies: Optional[dict[str, str]] = None,
                set_main_url_req: bool = False,
                force_session: Optional[Union[requests.Session, Requester]] = None
                ) -> BeautifulSoup:
        """Request a web page and return a BeautifulSoup object.

        Args:
            url (str): Url to request
            proxies: Provide proxy options to the underlying call
            set_main_url_req: If True, will set the soup for the main page to this

        Returns:
            bs4.BeautifulSoup: BeautifulSoup object representing the requested page's html
        """

        req = self.get(url, proxies=proxies, force_session=force_session)
        if len(req.content) > 650000:
            warnings.warn(
                "This work is very big and might take a very long time to load"
            )
        if set_main_url_req:
            self._main_page_rep = req

        soup = BeautifulSoup(req.content, "lxml")

        soup.status_code = req.status_code

        return soup

    def get(
        self,
        url: str,
        proxies: Optional[dict[str, str]] = None,
        allow_redirects: bool = True,
        timeout: Optional[Union[float, tuple[float, float]]] = None,
        force_session: Optional[requests.Session] = None
    ) -> requests.Response:
        """
        Request a web page and return a Response object.

        """

        from ao3.requester import requester

        if force_session is None:

            if self._session is None:
                req = requester.request(
                    method="get", url=url, allow_redirects=allow_redirects, timeout=timeout, proxies=proxies
                )
            else:
                req = requester.request(
                    method="get",
                    url=url,
                    allow_redirects=allow_redirects,
                    force_session=self._session.session,
                    timeout=timeout,
                    proxies=proxies
                )

        else:

            req = requester.request(
                method="get",
                url=url,
                allow_redirects=allow_redirects,
                force_session=force_session,
                timeout=timeout,
                proxies=proxies
            )

        from ao3 import utils

        if req.status_code == 429:
            raise errors.HTTPException(
                "We are being rate-limited. Try again in a while or reduce the number of requests"
            )
        return req

    def post(
        self,
        url: str,
        params: Optional[
            Union[
                dict[str, Union[str, int, float, bool]],
                list[tuple[str, Union[str, int, float, bool]]],
                bytes,
            ]
        ] = None,
        allow_redirects: bool = False,
        headers: Optional[dict[str, str]] = None,
        data: Optional[dict[str, str]] = None,
        force_session: Optional[requests.Session] = None
    ):
        """Make a post request with the current session

        Returns:
            requests.Request
        """

        if force_session is None:
            req = self.session.post(
                url=url,
                params=params,
                allow_redirects=allow_redirects,
                headers=headers,
                data=data,
            )
        else:
            req = force_session.post(
                url=url,
                params=params,
                allow_redirects=allow_redirects,
                headers=headers,
                data=data,
            )


        from ao3 import utils

        if req.status_code == 429:
            raise errors.RateLimitedException(
                "We are being rate-limited. Try again in a while or reduce the number of requests"
            )
        return req
