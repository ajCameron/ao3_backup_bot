
import requests
from bs4 import BeautifulSoup
from ao3.session.api import GuestAo3Session

LOGIN_PAGE = '''
<html><body>
<form>
  <input name="authenticity_token" value="TOKEN123"/>
</form>
</body></html>
'''

def test_authenticity_token_parsing():
    soup = BeautifulSoup(LOGIN_PAGE, "html.parser")
    token = soup.find("input", {"name":"authenticity_token"}).get("value")
    assert token == "TOKEN123"
