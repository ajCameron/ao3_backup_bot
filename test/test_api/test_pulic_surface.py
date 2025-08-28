
"""
Tests that we can run the imports we expect from the public surface.
"""

class TestPulicSurfaceImports:
    """
    Mostly to check for import loops and the like.
    """
    def test_basic_class_imports(self) -> None:
        """
        Tests we can import the basic, expected classes.

        :return:
        """
        from ao3 import utils
        assert utils is not None

        from ao3 import Work
        assert Work is not None

        from ao3 import Chapter
        assert Chapter is not None

        from ao3 import Ao3Session
        assert Ao3Session is not None
        from ao3 import GuestAo3Session
        assert GuestAo3Session is not None

        from ao3 import Comment
        assert Comment is not None
