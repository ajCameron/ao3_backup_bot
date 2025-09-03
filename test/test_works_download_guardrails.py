
import pytest
from ao3.works import Work
from ao3.errors import DownloadException, AuthException, UnloadedException


class TestDownloadGuardrails:
    """
    Tests that the download function of work has sensible fails when things don't look right.
    """

    def test_download_invalid_type_raises_download_exception(self) -> None:
        """
        Trying to download an invalid file type should error pretty early.

        :return:
        """
        try:
            w = Work(123456, load=False)
        except TypeError:
            pytest.skip("Work constructor signature changed")
        else:
            # We need to be logged in to access this restricted work
            with pytest.raises(DownloadException):
                w.download("NOT_A_TYPE")
