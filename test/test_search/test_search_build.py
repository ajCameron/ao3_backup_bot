
from ao3 import search, utils


def test_search_query_fields_build() -> None:
    """
    Tests building a search object.

    :return:
    """

    search_object = search.Search(
        any_field="spaceship",
        title="alpha",
        single_chapter=True,
        word_count=utils.Constraint(1000, 5000),
        language="en",
        rating="G"
    )

    assert search_object is not None

