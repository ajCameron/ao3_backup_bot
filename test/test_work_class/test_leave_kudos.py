
"""
Tests the leave kudos function under work.
"""


import os
import tempfile

import pytest

import ao3
import utils


class TestWorkLeaveKudos:
    """
    Try and download a work.
    """
    # def test_work_leave_kudos_guest_session(self) -> None:
    #     """
    #     Tests to see what happens if we leave kudos on the work.
    #
    #     As this changes the archive, not part of the regular test suite.
    #     :return:
    #     """
    #
    #     url = "https://archiveofourown.org/works/67764391/chapters/175195496"
    #     workid = ao3.utils.workid_from_url(url)
    #
    #     from ao3.session import GuestSession
    #
    #     work = ao3.Work(workid, session=GuestSession(), load_chapters=True, load=True)
    #
    #     work.leave_kudos()