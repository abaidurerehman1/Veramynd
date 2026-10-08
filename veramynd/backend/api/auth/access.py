"""Who may use Veramynd.

Optional access list, set on the server:
  VERAMYND_ALLOWED_EMAILS   comma-separated addresses, e.g. "ana@school.org,raj@school.org"
  VERAMYND_ALLOWED_DOMAINS  comma-separated email domains, e.g. "paisoltechnology.com"

When either is set, only matching accounts can sign up, sign in or use the API.
When neither is set, any verified account is allowed (the previous behaviour).
"""

from __future__ import annotations

import os


def _env_set(name: str) -> set[str]:
    return {x.strip().lower().lstrip("@") for x in os.getenv(name, "").split(",") if x.strip()}


def access_restricted() -> bool:
    return bool(_env_set("VERAMYND_ALLOWED_EMAILS") or _env_set("VERAMYND_ALLOWED_DOMAINS"))


def email_allowed(email: str | None) -> bool:
    """True if this email may use the app under the current access list."""
    if not access_restricted():
        return True
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        return False
    return e in _env_set("VERAMYND_ALLOWED_EMAILS") or e.rsplit("@", 1)[1] in _env_set("VERAMYND_ALLOWED_DOMAINS")


NOT_ALLOWED = "This email does not have access to Veramynd. Ask an administrator to add it."
