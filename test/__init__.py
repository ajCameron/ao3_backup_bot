
"""
Need a module structure to get useful test fixtures.
"""

import json

from ao3.session.api import Ao3Session

import os


def get_secrets_dict() -> dict[str, str]:
    """
    Return the username and password combo.

    :return:
    """
    secrets_path = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "secrets.json")

    assert os.path.exists(secrets_path), f"Secrets not found at {secrets_path = }"

    with open(secrets_path, encoding="utf-8") as secrets_file:
        auth_details = json.load(secrets_file)

    return auth_details



def get_authed_session() -> Ao3Session:
    """
    Return an authenticated session.

    :return:
    """

    auth_details = get_secrets_dict()

    return Ao3Session(username=auth_details["username"], password=auth_details["password"])
