"""
Stores and retrieves credential sets for access and login.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, List, Tuple

from ao3.session.ao3session import Ao3Session

from ao3_backup.config import CREDENTIALS_FILE, COOLDOWN_SECONDS, USER_AGENT


class CredentialRecord:
    """
    Creates a record for one of the sets of credentials pulled off disk.
    """

    def __init__(self, username: str, password: str) -> None:
        """
        Startup the manager.

        :param username:
        :param password:
        """
        self.username = username
        self.password = password
        self.session: Optional[Ao3Session] = None
        self.last_used = 0.0
        self.cooldown_until = 0.0

    def ensure_session(self) -> Ao3Session:
        """
        Create and store an authenticated session for the given credentials.

        :return:
        """
        if self.session is None:
            s = Ao3Session(username=self.username, password=self.password)
            # Todo: Actually set this up
            # Todo: Extend this with the means of watching people's bookmarks and stuff like that
            try:
                s.session_requester.set_user_agent(USER_AGENT)
            except Exception:
                pass
            self.session = s
        return self.session

    def is_available(self) -> bool:
        """
        Is this token still on cooldown?

        :return:
        """
        return time.time() >= self.cooldown_until

    def mark_used(self) -> None:
        """
        Mark this set of credentials as having been used at this time.

        :return:
        """
        self.last_used = time.time()

    def cooldown(self, seconds: int) -> None:
        """
        Set a cooldown period for this token.

        :param seconds:
        :return:
        """
        self.cooldown_until = max(self.cooldown_until, time.time() + seconds)


class CredentialManager:
    def __init__(self, path: Path = CREDENTIALS_FILE):
        self.path = Path(path)
        self.records: List[CredentialRecord] = []
        self._load()

    # Todo: block_till_token - wait util the cooldown is over for a token, then give me a token.

    def _load(self):
        self.records.clear()
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for item in data:
            self.records.append(CredentialRecord(item["username"], item["password"]))

    def _save(self):
        data = [{"username": r.username, "password": r.password} for r in self.records]
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, username: str, password: str):
        if any(r.username == username for r in self.records):
            return False
        self.records.append(CredentialRecord(username, password))
        self._save()
        return True

    def remove(self, username: str):
        self.records = [r for r in self.records if r.username != username]
        self._save()

    def list(self) -> List[Tuple[str, bool, float]]:
        now = time.time()
        return [
            (r.username, r.is_available(), max(0.0, r.cooldown_until - now))
            for r in self.records
        ]

    def pick(self) -> Optional[CredentialRecord]:
        candidates = [r for r in self.records if r.is_available()]
        if not candidates:
            return None
        candidates.sort(key=lambda r: r.last_used)
        return candidates[0]

    def mark_rate_limited(self, username: str):
        for r in self.records:
            if r.username == username:
                r.cooldown(COOLDOWN_SECONDS)
                break
