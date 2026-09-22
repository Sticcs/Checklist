"""Per-task, in-memory presence ('who's viewing this assignment right
now'). Lives in FastAPI process memory: lost on restart, and only correct
with a single uvicorn worker (the default) - same non-regression reasoning
as undo.py, just for a feature that never existed before rather than one
being ported. A per-task entry is never explicitly removed (only individual
stale usernames are pruned on read) - negligible in practice, bounded by
however many distinct assignments have ever been opened, not by traffic.
"""

import time

ONLINE_WINDOW_SECONDS = 45  # ~2.25x AssignmentWorkspace's 20s poll interval

_last_seen: dict[int, dict[str, float]] = {}


def heartbeat(task_id: int, username: str) -> None:
    _last_seen.setdefault(task_id, {})[username] = time.time()


def online_users(task_id: int) -> list[str]:
    seen = _last_seen.get(task_id)
    if not seen:
        return []
    cutoff = time.time() - ONLINE_WINDOW_SECONDS
    for stale_username in [u for u, ts in seen.items() if ts < cutoff]:
        del seen[stale_username]
    return sorted(seen.keys())
