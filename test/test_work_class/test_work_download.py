
import pytest

import os
import tempfile

import ao3

from .. import get_secrets_dict


class TestDownloadAWork:
    """
    Try and download a work.
    """
    def test_download_unrestricted_work_guest_session(self) -> None:
        """
        Tests downloading an unrestricted work using a Guest Session.

        This is prefered - we don't want to use logged in credentials unless we HAVE to.
        :return:
        """

        url = "https://archiveofourown.org/works/67764391/chapters/175195496"
        workid = ao3.utils.workid_from_url(url)

        from ao3.session.api import GuestAo3Session

        work = ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)

        with tempfile.TemporaryDirectory() as tmpdirname:

            target_file_path = os.path.join(tmpdirname, f"{work.title}.pdf")

            with open(target_file_path, "wb") as file:
                file.write(work.download("PDF"))

            assert os.path.exists(target_file_path) and os.path.isfile(target_file_path)

            assert os.path.getsize(target_file_path) >= 211489

    def test_download_age_restricted_work_guest_session(self) -> None:
        """
        Some works seem to need you to agree to an age restriction before viewing.

        Hacking on that.
        :return:
        """
        url = "https://archiveofourown.org/works/67662711/chapters/174904496"
        workid = ao3.utils.workid_from_url(url)

        from ao3.session.api import GuestAo3Session

        work = ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)

        with tempfile.TemporaryDirectory() as tmpdirname:

            target_file_path = os.path.join(tmpdirname, f"{work.title}.pdf")

            with open(target_file_path, "wb") as file:
                file.write(work.download("PDF"))

            assert os.path.exists(target_file_path) and os.path.isfile(target_file_path)

            assert os.path.getsize(target_file_path) >= 225463

    def test_download_access_restricted_work_guest_session(self) -> None:
        """
        Some works seem to need you to agree to an age restriction before viewing.

        Hacking on that.
        :return:
        """
        target_url = "https://archiveofourown.org/works/2"

        workid = ao3.utils.workid_from_url(target_url)
        assert workid == 2, f"Unexpected workid - {workid}"

        from ao3.session.api import GuestAo3Session

        test_work = ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)

        try:
            test_work.download("PDF")
        except Exception as e:
            assert type(e) is ao3.errors.AuthException

    def test_download_access_restricted_work_authed_session(self) -> None:
        """
        Some works seem to need you to agree to an age restriction before viewing.

        Hacking on that.
        :return:
        """
        url = "https://archiveofourown.org/works/2"
        workid = ao3.utils.workid_from_url(url)

        from ao3.session.api import Ao3Session

        secrets_dict = get_secrets_dict()

        test_session = Ao3Session(
            username=secrets_dict["username"], password=secrets_dict["password"]
        )

        work = ao3.Work(workid, session=test_session, load_chapters=True, load=True)

        with tempfile.TemporaryDirectory() as tmpdirname:

            target_file_path = os.path.join(tmpdirname, f"{work.title}.pdf")

            with open(target_file_path, "wb") as file:
                file.write(work.download("PDF"))

            assert os.path.exists(target_file_path) and os.path.isfile(target_file_path)

            assert os.path.getsize(target_file_path) >= 82563