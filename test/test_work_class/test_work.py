
"""
We're testing the work class.

This represents a work on the archive - and then allows us to do useful stuff with it.
"""

import ao3

import pytest

import errors
import utils


class TestWorkBadStory:
    """
    Not actually bad - just doesn't actually exist.
    """
    def test_work_story_1(self) -> None:
        """
        We're going to load story 1.

        This should fail with a 404 - as the story does, in fact, not exist anymore.
        :return:
        """
        target_url = "https://archiveofourown.org/works/1"

        workid = ao3.utils.workid_from_url(target_url)
        assert workid == 1, f"Unexpected workid - {workid}"

        from ao3.session import GuestAo3Session

        with pytest.raises(errors.WorkNotFoundInvalidIdException):
            ao3.Work(workid, session=GuestAo3Session(), load_chapters=True, load=True)




