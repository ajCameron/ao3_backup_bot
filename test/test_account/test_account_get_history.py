
"""
Diving into and debugging the account.get_history method - because something seems to be going wrong.
"""
import datetime
from typing import Optional, Union

import bs4
import re

import pytest
from bs4 import BeautifulSoup


import warnings
import requests

from ao3.errors import LoginException, AuthException
from ao3.session.api import Ao3Session, Ao3SessionUnPooled
from ao3.requester import Requester
from ao3.works import Work
from ao3.account import Account
from ao3.utils import ao3_parse_date, ao3_parse_int
from ao3.models import HistoryItem


from test import get_secrets_dict


class TestAccountGetHistory:
    """
    Breaking down the get_history method, to check that we're parsing the soup properly.

    Or it could just be taking a really long time.
    """

    def test_get_history_direct_call(self) -> None:
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

        test_account_history = test_account.get_history()

        assert isinstance(test_account_history, list)
        for hist_item in test_account_history:
            assert isinstance(hist_item, HistoryItem)

    def test_get_history_flow_prototype(self) -> None:
        """
        Basic tests for the get_history flow.

        :return:
        """
        secrets_dict = get_secrets_dict()

        test_session = Ao3SessionUnPooled(
            username=secrets_dict["username"], password=secrets_dict["password"]
        )

        assert test_session.logged_in is True

        test_account = Account(session=test_session)

        history_page_url = test_account.get_history_page_url(page=1)
        assert test_account.get_history_page_url(page=1) \
               == \
               "https://archiveofourown.org/users/thomaswpaine/readings?page=1"

        soup = test_account.request(history_page_url)

        assert soup.title.string == "History | Archive of Our Own"

        root = soup
        assert root.find_all("li", attrs={"role": "article"}, recursive=False) == []

        def _retry_test(target_soup: bs4.BeautifulSoup) -> Optional[bs4._typing._AtMostOneElement]:
            return target_soup.find("ol", {"class": "reading work index group"})

        history = _retry_test(soup)

        _history = []

        assert len(history.find_all("li", {"role": "article"})) > 1

        for item in history.find_all("li", {"role": "article"}):

            # Title
            h = item.find("h4", class_=re.compile(r"\bheading\b"))
            a_title = h.find("a", href=re.compile(r"/works/\d+")) if h else None
            title = a_title.get_text(strip=True) if a_title else ""

            assert isinstance(title, str)

            # Work ID
            work_id = None
            if a_title and a_title.has_attr("href"):
                m = re.search(r"/works/(\d+)", a_title["href"])
                if m:
                    work_id = int(m.group(1))

            assert isinstance(work_id, int)

            # Authors
            authors = [a.get_text(strip=True) for a in
                       (h.find_all("a", attrs={"rel": "author"}) if h else [])
                       ]
            assert isinstance(authors, list)
            for auth in authors:
                assert isinstance(auth, str)

            # Datetime (AO3 often has <p class="datetime">12 Jan 2023</p>)
            dt = None
            p_dt = item.find("p", class_=re.compile(r"\bdatetime\b"))
            if p_dt:
                dt = ao3_parse_date(p_dt.get_text(" ", strip=True))
            assert isinstance(dt, datetime.datetime)

            # Chapter count and word count in the blurb meta (<dd> or spans)
            chapter_count = None
            words = None
            dd_tags = item.find_all(["dd", "span"])
            for dd in dd_tags:
                label = dd.get("class") or []
                txt = dd.get_text(" ", strip=True)
                if any("chapters" in c for c in label):
                    chapter_count = ao3_parse_int(txt)
                elif "words" in txt.lower() or any("words" in c for c in label):
                    words = ao3_parse_int(txt)
            assert isinstance(chapter_count, int)
            assert isinstance(words, int)

            visited_date = None
            visited_num = 1
            for viewed in item.find_all("h4", {"class": "viewed heading"}):
                data_string = str(viewed)
                date_str = re.search(
                    "<span>Last visited:</span> (\d{2} .+ \d{4})", data_string
                )
                if date_str is not None:
                    date_time_obj = datetime.datetime.strptime(
                        date_str.group(1), "%d %b %Y"
                    )
                    visited_date = date_time_obj

                visited_str = re.search("Visited (\d+) times", data_string)
                if visited_str is not None:
                    visited_num = int(visited_str.group(1))
            assert isinstance(visited_date, datetime.datetime)
            assert isinstance(visited_num, int)

            new = HistoryItem(
                work_id=work_id,
                work_title=title,
                last_read_at=dt,
                authors=authors,
                chapter_count=chapter_count,
                words=words,
                visited_date=visited_date,
                visited_num=visited_num
            )

            if new not in _history:
                _history.append(new)


