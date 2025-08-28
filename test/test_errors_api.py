
"""
Tests the errors API.
"""


import ao3
from ao3 import errors as errs


def test_exception_hierarchy():
    """
    Tests all the exceptions inherit properly.

    :return:
    """
    for cls_name in [
        "AO3Exception","LoginException","UnloadedException","NetworkException",
        "UnexpectedResponseException","HTTPException","RateLimitedException",
        "InvalidIdException","WorkNotFoundException","DownloadException",
        "AuthException","DuplicateCommentException","PseudException",
        "BookmarkException","CollectException",
    ]:
        cls = getattr(errs, cls_name)
        assert issubclass(cls, errs.AO3Exception)


def test_public_exports():
    """
    Tests the public API contains the minimal selection of Exceptions.

    :return:
    """
    api = set(getattr(ao3, "__all__", []))
    assert "Work" in api
    assert "Ao3Session" in api
    assert hasattr(ao3, "NetworkException")
