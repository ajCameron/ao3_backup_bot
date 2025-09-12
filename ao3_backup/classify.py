from __future__ import annotations

RESTRICTED_MARKERS = [
    "This work is only available to registered users of AO3",
    "This work is only available to users 18 and older",
    "Log in to access more works",
]
UNREVEALED_MARKERS = [
    "This work is unrevealed",
    "This work will be revealed",
]


def classify_response(url: str, status_code: int, text: str, final_url: str) -> str:
    if status_code == 404:
        return "not_found"
    if "users/login" in (final_url or ""):
        return "restricted"
    lower = (text or "").lower()
    if any(m.lower() in lower for m in RESTRICTED_MARKERS):
        return "restricted"
    if any(m.lower() in lower for m in UNREVEALED_MARKERS):
        return "unrevealed"
    if status_code == 200:
        return "public"
    if status_code in (401, 403):
        return "restricted"
    return "error"
