
import os
import json
import pytest
import requests

@pytest.fixture(scope="session")
def secrets():
    path = os.getenv("AO3_SECRETS_JSON", "secrets.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

@pytest.fixture()
def session_obj():
    return requests.Session()
