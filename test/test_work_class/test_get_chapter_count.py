import ao3
from ao3.errors import AuthException

import pytest


class TestGetChapterCount:
    """
    Tests that we an get the chapter count of a work.
    """

    def test_get_chapter_count_restricted_work_guest_session(self) -> None:
        """
        We're trying to load up a restricted work with a guest session.

        This is not gonna work very well at all.
        :return:
        """

        url = "https://archiveofourown.org/works/14392692/chapters/33236241"
        workid = ao3.utils.workid_from_url(url)

        assert workid == 14392692, f"Unexpected work id {workid}"

        from ao3.session.api import GuestAo3Session

        work = ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)

        assert work.restricted is True, "This work should be restricted."

        assert work._soup.find_all("dd") is not None, "Even on the login page, there should be some."

        with pytest.raises(AuthException):
            # This doesn't seem right
            assert work.nchapters == 0, f"Unexpected chapters count - {work.nchapters}"

    def test_get_chapter_count_unrestricted_work_guest_session(self) -> None:
        """
        We're trying to load an unrestricted work.

        This should work a lot better.
        :return:
        """
        url = "https://archiveofourown.org/works/67764391/chapters/175195496"
        workid = ao3.utils.workid_from_url(url)

        assert workid == 67764391, f"Unexpected work id {workid}"

        from ao3.session.api import GuestAo3Session

        work = ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)

        # It's age restricted, but not restricted... Not sure if this is a problem
        assert work.restricted is False, "This work should NOT be restricted."

        assert work._soup.find_all("dd") is not None, "Even on the login page, there should be some."

        assert work.nchapters == 3, f"Unexpected chapters count - {work.nchapters}"


