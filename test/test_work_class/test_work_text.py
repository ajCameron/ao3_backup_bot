
import os
import tempfile
import ao3

import pytest


class TestWorkMetadata:
    """
    Try and download a work.
    """
    def test_work_metadata_guest_session(self) -> None:
        """
        Tetss
        :return:
        """

        url = "https://archiveofourown.org/works/67764391/chapters/175195496"
        workid = ao3.utils.workid_from_url(url)

        from ao3.session.api import GuestAo3Session

        work = ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)

        assert isinstance(work.text, str)

        if work.text == 0:
            err_str = "We're getting that transitory bug - investigating."
            err_str += f"\n{work._soup.title = }"
            pytest.fail(err_str)

        assert len(work.text) >= 100000, f"Full text for the work was not as long as expected - {work.text = }"



