import uuid

import bcrypt
from fastapi import Cookie, HTTPException, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="auth-cookie")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        # Malformed/legacy hash that bcrypt can't parse - treat as no match
        # rather than raising, so a bad stored value can't 500 the login route.
        return False


def make_guest_username() -> str:
    # Every guest session gets its own throwaway identity instead of sharing a
    # literal "guest" username, so two separate guest logins never collide on
    # the same task rows.
    return f"guest_{uuid.uuid4().hex[:12]}"


def set_session_cookie(response: Response, username: str, is_guest: bool, remember: bool = True) -> None:
    # remember=False (an unchecked "keep me logged in" box - see routers/
    # auth.py's /login) sends max_age=None, which omits Max-Age/Expires
    # entirely and makes it a plain session cookie: the browser drops it
    # once it's actually closed, rather than it quietly lasting 30 days
    # regardless. get_current_user's own signature-staleness check still
    # uses the full cookie_max_age either way - that's just an upper bound
    # on how old a *signature* can be, not what controls how long the
    # browser holds onto the cookie.
    token = _serializer.dumps({"username": username, "is_guest": is_guest})
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=settings.cookie_max_age if remember else None,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.cookie_name)


class CurrentUser:
    def __init__(self, username: str, is_guest: bool):
        self.username = username
        self.is_guest = is_guest


def get_current_user(session: str | None = Cookie(default=None)) -> CurrentUser:
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        # max_age here matches the cookie's own max_age - an old but
        # not-yet-expired cookie value should still be accepted.
        payload = _serializer.loads(session, max_age=settings.cookie_max_age)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    return CurrentUser(username=payload["username"], is_guest=payload["is_guest"])
