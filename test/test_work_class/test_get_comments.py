
import os
import tempfile
import ao3
from ao3.comments import Comment


class TestWorkGetComments:
    """
    Try and download a work.
    """
    def test_work_metadata_guest_session_work_with_no_comments(self) -> None:
        """
        Tetss
        :return:
        """

        url = "https://archiveofourown.org/works/67764391/chapters/175195496"
        workid = ao3.utils.workid_from_url(url)

        from ao3.session import GuestSession

        work = ao3.Work(workid, session=GuestSession(), load_chapters=True, load=True)

        comments = work.get_comments()

        assert isinstance(comments, list)

        for comment in comments:
            assert isinstance(comment, Comment)

        assert len(comments) >= 7