from fastapi import APIRouter, Depends, HTTPException, Response, status

from app import crud
from app.models import LoginRequest, SignupRequest, UserResponse
from app.security import (
    CurrentUser,
    clear_session_cookie,
    get_current_user,
    make_guest_username,
    set_session_cookie,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest) -> dict:
    if not body.username.strip() or not body.password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username and password are required")
    if not crud.create_user(body.username, body.password):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")
    return {"username": body.username.strip()}


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, response: Response) -> UserResponse:
    if not crud.verify_user(body.username, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    username = body.username.strip()
    set_session_cookie(response, username, is_guest=False)
    return UserResponse(username=username, is_guest=False)


@router.post("/guest", response_model=UserResponse)
def guest(response: Response) -> UserResponse:
    username = make_guest_username()
    set_session_cookie(response, username, is_guest=True)
    return UserResponse(username=username, is_guest=True)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    clear_session_cookie(response)


@router.get("/me", response_model=UserResponse)
def me(current_user: CurrentUser = Depends(get_current_user)) -> UserResponse:
    return UserResponse(username=current_user.username, is_guest=current_user.is_guest)
