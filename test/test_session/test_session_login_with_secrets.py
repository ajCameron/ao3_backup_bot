
import os
import pytest
from ao3.session import Ao3Session

@pytest.mark.skipif(not os.path.exists(os.getenv("AO3_SECRETS_JSON", "../secrets.json")), reason="no secrets.json available")
def test_real_login_roundtrip(secrets):
    s = Ao3Session()
    s.login(secrets["username"], secrets["password"])
    assert getattr(s, "is_authed", False) is True
