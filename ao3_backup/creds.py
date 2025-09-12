
"""
Stores 
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, List, Tuple

from ao3.session.ao3session import Ao3Session

from .config import CREDENTIALS_FILE, COOLDOWN_SECONDS, USER_AGENT


class CredentialRecord:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.session: Optional[Ao3Session] = None
        self.last_used = 0.0
        self.cooldown_until = 0.0

    def ensure_session(self) -> Ao3Session:
        if self.session is None:
            s = Ao3Session()
            s.login(self.username, self.password)
            try:
                s.session_requester.set_user_agent(USER_AGENT)
            except Exception:
                pass
            self.session = s
        return self.session

    def is_available(self) -> bool:
        return time.time() >= self.cooldown_until

    def mark_used(self):
        self.last_used = time.time()

    def cooldown(self, seconds: int):
        self.cooldown_until = max(self.cooldown_until, time.time() + seconds)


class CredentialManager:
    def __init__(self, path: Path = CREDENTIALS_FILE):
        self.path = Path(path)
        self.records: List[CredentialRecord] = []
        self._load()

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
