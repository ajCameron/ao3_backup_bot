
import os
import tempfile
import ao3


class TestDownloadAWork:
    """
    Try and download a work.
    """
    def test_download_unrestricted_work_guest_session(self) -> None:
        """
        Tetss
        :return:
        """

        url = "https://archiveofourown.org/works/67764391/chapters/175195496"
        workid = ao3.utils.workid_from_url(url)

        from ao3.session import GuestSession

        work = ao3.Work(workid, session=GuestSession(), load_chapters=True, load=True)

        with tempfile.TemporaryDirectory() as tmpdirname:

            target_file_path = os.path.join(tmpdirname, f"{work.title}.pdf")

            with open(target_file_path, "wb") as file:
                file.write(work.download("PDF"))

            assert os.path.exists(target_file_path) and os.path.isfile(target_file_path)

            assert os.path.getsize(target_file_path) >= 211489
