from fastapi import APIRouter, Depends, HTTPException, status

from app import crud
from app.models import NotificationEntry, NotificationsResponse
from app.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _entry(row: dict) -> NotificationEntry:
    return NotificationEntry(
        id=row["id"],
        kind=row["kind"],
        message=row["message"],
        actor_username=row["actor_username"],
        task_id=row["task_id"],
        created_at=row["created_at"],
        read=row["read_at"] is not None,
    )


@router.get("", response_model=NotificationsResponse)
def list_notifications(
    limit: int = 30, current_user: CurrentUser = Depends(get_current_user)
) -> NotificationsResponse:
    rows = crud.list_notifications(current_user.username, limit=limit)
    unread_count = crud.unread_notification_count(current_user.username)
    return NotificationsResponse(notifications=[_entry(r) for r in rows], unread_count=unread_count)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(notification_id: int, current_user: CurrentUser = Depends(get_current_user)) -> None:
    if not crud.mark_notification_read(notification_id, current_user.username):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(current_user: CurrentUser = Depends(get_current_user)) -> None:
    crud.mark_all_notifications_read(current_user.username)
