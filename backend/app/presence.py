"""Per-task, in-memory presence ('who's viewing this assignment right
now', and which page they're on). Lives in FastAPI process memory: lost on
restart, and only correct with a single uvicorn worker (the default) - same
non-regression reasoning as undo.py, just for a feature that never existed
before rather than one being ported. A per-task entry is never explicitly
removed (only individual stale usernames are pruned on read) - negligible in
practice, bounded by however many distinct assignments have ever been
opened, not by traffic.
"""

import time

ONLINE_WINDOW_SECONDS = 10  # ~2.5x AssignmentWorkspace's 4s poll interval

_last_seen: dict[int, dict[str, float]] = {}
# Which page (WorkspacePage.id) each username last reported being on - the
# "follow where someone's typing" feature (click their presence avatar to
# jump to their page) reads this. None if they weren't on a specific page.
_page: dict[int, dict[str, str | None]] = {}


def heartbeat(task_id: int, username: str, page_id: str | None = None) -> None:
    _last_seen.setdefault(task_id, {})[username] = time.time()
    _page.setdefault(task_id, {})[username] = page_id


def online_users(task_id: int) -> list[dict]:
    seen = _last_seen.get(task_id)
    if not seen:
        return []
    cutoff = time.time() - ONLINE_WINDOW_SECONDS
    pages = _page.setdefault(task_id, {})
    for stale_username in [u for u, ts in seen.items() if ts < cutoff]:
        del seen[stale_username]
        pages.pop(stale_username, None)
    return [{"username": u, "page_id": pages.get(u)} for u in sorted(seen.keys())]
