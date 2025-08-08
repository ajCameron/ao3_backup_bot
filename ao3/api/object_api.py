"""
Holds the base class for all AO3 objects.
"""

from functools import cached_property

import requests

import bs4
from bs4 import BeautifulSoup

from ao3 import utils
from ao3.requester import requester


class BaseObjectAPI:

    # Todo: These should probably sod off and become part of a base class
    def request(self, url: str) -> BeautifulSoup:
        """Request a web page and return a BeautifulSoup object.

        Args:
            url (str): Url to request

        Returns:
            bs4.BeautifulSoup: BeautifulSoup object representing the requested page's html
        """

        req = self.get(url)
        soup = BeautifulSoup(req.content, "lxml")
        return soup

    def get(self, url: str) -> requests.Response:
        """Request a web page and return a Response object"""

        if self._session is None:
            req = requester.request("get", url=url)
        else:
            req = requester.request("get", url=url, session=self._session.session)
        if req.status_code == 429:
            raise utils.RateLimitError(
                "We are being rate-limited. Try again in a while or reduce the number of requests"
            )
        return req
