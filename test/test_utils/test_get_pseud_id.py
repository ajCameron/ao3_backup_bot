
import pytest

import ao3
import errors
from ao3.utils import get_pseud_id


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

        from ao3.session import GuestSession

        work = ao3.Work(workid, session=GuestSession(), load_chapters=True, load=True)

        with pytest.raises(errors.AuthException):
            assert get_pseud_id(work) == ""
