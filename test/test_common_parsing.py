
from bs4 import BeautifulSoup
from ao3.common import get_work_from_banner

HTML = '''
<li role="article">
  <h4 class="heading">
    <a href="/works/123456">Example Title</a>
    <a rel="author" href="/users/Foo/pseuds/Foo">Foo</a>
  </h4>
  <p class="datetime">12 Jan 2023</p>
  <span class="kudos">Kudos: 42</span>
  <span class="bookmarks">Bookmarks: 7</span>
</li>
'''


def test_get_work_from_banner_smoke():
    """
    Smoke test get_work_from_banner.

    :return:
    """
    soup = BeautifulSoup(HTML, "html.parser")
    li = soup.find("li", {"role":"article"})
    work = get_work_from_banner(li)
    assert work is not None
    assert hasattr(work, "authors")
