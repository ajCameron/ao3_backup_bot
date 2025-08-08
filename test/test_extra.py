

from ao3.extra import get_resources, download_all, download_all_threaded


class TestExtra:
    """
    Tests the extra functions.
    """
    def test_download_all_get_resources_rwe(self) -> None:
        """
        Tests the get_resources function rwe.

        :return:
        """
        download_all()

        resources = get_resources()

        assert isinstance(resources, dict)

    def test_download_all_threaded_get_resources_rwe(self) -> None:
        """
        Tests the get_resources function rwe.

        :return:
        """
        download_all_threaded()

        resources = get_resources()

        assert isinstance(resources, dict)
        assert sorted([rk for rk in resources.keys()]) == ['fandoms', 'languages']

        assert resources["languages"] == ['languages']
