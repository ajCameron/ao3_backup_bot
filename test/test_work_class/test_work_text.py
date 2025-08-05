
import os
import tempfile
import ao3


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

        assert isinstance(work.text, str)

        assert len(work.text) >= 100000

