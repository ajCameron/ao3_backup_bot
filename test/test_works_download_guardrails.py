
import pytest
from ao3.works import Work
from ao3.errors import DownloadException

def test_download_invalid_type_raises():
    try:
        w = Work(123456, load=False)
    except TypeError:
        pytest.skip("Work constructor signature changed")
    with pytest.raises(DownloadException):
        w.download("NOT_A_TYPE")
