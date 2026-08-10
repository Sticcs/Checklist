from datetime import datetime

from fastapi import APIRouter, Depends, Response

from app import crud
from app.models import ExportPayload, ImportResponse
from app.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api", tags=["data"])


@router.get("/export", response_model=ExportPayload)
def export_data(response: Response, current_user: CurrentUser = Depends(get_current_user)) -> ExportPayload:
    # response_model does the actual field filtering here - get_tasks_with_subtasks
    # returns full rows (id, username, position, ...), but ExportPayload only
    # declares the portable subset, so FastAPI drops the rest on serialization.
    response.headers["Content-Disposition"] = 'attachment; filename="checklist-export.json"'
    tasks = crud.get_tasks_with_subtasks(current_user.username)
    return ExportPayload(exported_at=datetime.now().isoformat(), tasks=tasks)


@router.post("/import", response_model=ImportResponse)
def import_data(payload: ExportPayload, current_user: CurrentUser = Depends(get_current_user)) -> ImportResponse:
    imported_tasks, imported_subtasks = crud.import_data(
        [t.model_dump() for t in payload.tasks], current_user.username
    )
    return ImportResponse(imported_tasks=imported_tasks, imported_subtasks=imported_subtasks)
