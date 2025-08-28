
import ao3
from ao3 import utils

def test_workid_from_url_variants():
    urls = [
        "https://archiveofourown.org/works/123456",
        "https://archiveofourown.org/works/123456/chapters/654321",
        "https://archiveofourown.org/works/123456?view_full_work=true",
    ]
    for u in urls:
        wid = utils.workid_from_url(u)
        assert wid == 123456

def test_word_count():
    assert utils.word_count("one two  three\nfour\t") == 4
    assert utils.word_count("") == 0

def test_url_join():
    from ao3.common import url_join
    assert url_join("https://a/b", "c") == "https://a/b/c"

def test_querybuilder_and_constraint():
    q = utils.QueryBuilder()
    q.add_field("a=1")
    q.add_field("b=two")
    assert "a=1" in q.string and "b=two" in q.string
    c = utils.Constraint(10, 20)
    assert isinstance(c, utils.Constraint)
