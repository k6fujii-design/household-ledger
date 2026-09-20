from datetime import date

from fastapi import APIRouter, Depends, Query

from app.routers.deps import current_user
from app.schemas.report import SummaryResponse
from app.store import DynamoStore, get_store

router = APIRouter(prefix="/api/reports", tags=["reports"])


def active_statuses(statuses: list[str] | None) -> list[str]:
    return statuses if statuses else ["new", "settled"]


@router.get("/summary", response_model=SummaryResponse, response_model_by_alias=False)
def summary(
    from_: date = Query(alias="from"),
    to: date = Query(),
    statuses: str | None = None,
    category: str | None = None,
    tag_id: str | None = None,
    store: DynamoStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    status_list = active_statuses(statuses.split(",") if statuses else None)
    return store.summarize(from_, to, status_list, category, tag_id)
