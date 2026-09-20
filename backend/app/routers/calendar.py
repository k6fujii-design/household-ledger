from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends

from app.routers.deps import current_user
from app.schemas.calendar import CalendarMonthResponse, CalendarYearResponse
from app.store import DynamoStore, get_store

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/month", response_model=CalendarMonthResponse)
def month(year: int, month: int, statuses: str | None = None, category: str | None = None, tag_id: str | None = None, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    status_list = statuses.split(",") if statuses else ["new", "settled"]
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    users = {row["email"]: row for row in store.list_users()}
    user_f = users.get("f@example.com")
    user_o = users.get("o@example.com")
    rows = store.list_tickets(first, last, statuses=status_list, category=category, tag_id=tag_id)
    by_day: dict[str, dict] = {}
    for ticket in rows:
        day = by_day.setdefault(ticket["date"], {"date": ticket["date"], "total_amount": 0, "ticket_count": 0, "paid_by_f": 0, "paid_by_o": 0})
        day["total_amount"] += ticket["amount"]
        day["ticket_count"] += 1
        if user_f and ticket["payer_user_id"] == user_f["id"]:
            day["paid_by_f"] += ticket["amount"]
        if user_o and ticket["payer_user_id"] == user_o["id"]:
            day["paid_by_o"] += ticket["amount"]
    return {"year": year, "month": month, "days": sorted(by_day.values(), key=lambda d: d["date"])}


@router.get("/year", response_model=CalendarYearResponse)
def year(year: int, statuses: str | None = None, category: str | None = None, tag_id: str | None = None, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    status_list = statuses.split(",") if statuses else ["new", "settled"]
    first = date(year, 1, 1)
    last = date(year, 12, 31)
    users = {row["email"]: row for row in store.list_users()}
    user_f = users.get("f@example.com")
    user_o = users.get("o@example.com")
    rows = store.list_tickets(first, last, statuses=status_list, category=category, tag_id=tag_id)
    by_month = {
        month: {"month": month, "total_amount": 0, "ticket_count": 0, "paid_by_f": 0, "paid_by_o": 0}
        for month in range(1, 13)
    }
    for ticket in rows:
        item = by_month[int(ticket["date"][5:7])]
        item["total_amount"] += ticket["amount"]
        item["ticket_count"] += 1
        if user_f and ticket["payer_user_id"] == user_f["id"]:
            item["paid_by_f"] += ticket["amount"]
        if user_o and ticket["payer_user_id"] == user_o["id"]:
            item["paid_by_o"] += ticket["amount"]
    return {"year": year, "months": list(by_month.values())}
