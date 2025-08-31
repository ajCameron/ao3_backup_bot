
import os
import pytest
from ao3.session.api import Ao3SessionUnPooled


@pytest.mark.skipif(not os.path.exists(os.getenv("AO3_SECRETS_JSON", "../secrets.json")), reason="no secrets.json available")
def test_real_login_roundtrip(secrets):
    s = Ao3SessionUnPooled(username=secrets["username"], password=secrets["password"])
