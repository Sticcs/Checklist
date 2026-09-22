from fastapi import APIRouter, Depends, HTTPException, status

from app import crud
from app.models import ChatMessageCreate, ChatMessageEntry, ChatMessagesResponse
from app.routers.collaboration import _require_assignment_access
from app.security import CurrentUser, get_current_user

# One shared group channel per assignment (task_id) - not 1:1 DMs. Same
# owner-or-collaborator gate as everything else in the workspace
# (_require_assignment_access, reused from collaboration.py rather than
# duplicated). No undo.save_snapshot() calls anywhere here - chat messages
# aren't part of tasks/subtasks state, which is all undo/redo ever restores.
router = APIRouter(prefix="/api/tasks", tags=["chat"])

MAX_MESSAGE_LENGTH = 2000


def _entry(row: dict) -> ChatMessageEntry:
    return ChatMessageEntry(id=row["id"], username=row["username"], text=row["text"], created_at=row["created_at"])


@router.get("/{task_id}/messages", response_model=ChatMessagesResponse)
def list_messages(task_id: int, current_user: CurrentUser = Depends(get_current_user)) -> ChatMessagesResponse:
    _require_assignment_access(task_id, current_user.username)
    rows = crud.list_chat_messages(task_id)
    unread = crud.unread_chat_count(task_id, current_user.username)
    return ChatMessagesResponse(messages=[_entry(r) for r in rows], unread_count=unread)


@router.post("/{task_id}/messages", response_model=ChatMessageEntry, status_code=status.HTTP_201_CREATED)
def post_message(
    task_id: int, body: ChatMessageCreate, current_user: CurrentUser = Depends(get_current_user)
) -> ChatMessageEntry:
    _require_assignment_access(task_id, current_user.username)
    stripped = body.text.strip()
    if not stripped:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message can't be empty")
    if len(stripped) > MAX_MESSAGE_LENGTH:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message is too long")
    row = crud.create_chat_message(task_id, current_user.username, stripped)
    return _entry(row)


@router.post("/{task_id}/messages/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_messages_read(task_id: int, current_user: CurrentUser = Depends(get_current_user)) -> None:
    _require_assignment_access(task_id, current_user.username)
    crud.mark_chat_read(task_id, current_user.username)
