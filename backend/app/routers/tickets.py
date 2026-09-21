from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.routers.deps import current_user
from app.schemas.ticket import BulkStatusRequest, BulkStatusResponse, BulkTagsRequest, BulkTagsResponse, TicketCreate, TicketOut, TicketUpdate
from app.store import DynamoStore, get_store

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketOut])
def list_tickets(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    status: str | None = None,
    category: str | None = None,
    payer_user_id: UUID | None = None,
    keyword: str | None = None,
    tag_id: str | None = None,
    tag_ids: str | None = None,
    store: DynamoStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    selected_tag_ids = [value for value in (tag_ids or "").split(",") if value]
    return store.list_tickets(from_, to, status=status, category=category, payer_user_id=payer_user_id, keyword=keyword, tag_id=tag_id, tag_ids=selected_tag_ids)


@router.post("", response_model=TicketOut)
def create_ticket(payload: TicketCreate, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    try:
        ticket = store.create_ticket(payload, UUID(user["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    store.write_audit(
        "ticket_create",
        "ticket",
        user["id"],
        ticket["id"],
        after=store.ticket_audit_dict(ticket),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ticket


@router.post("/bulk-status", response_model=BulkStatusResponse)
def bulk_status(payload: BulkStatusRequest, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    if payload.from_status != "new" or payload.to_status != "settled":
        raise HTTPException(status_code=400, detail="new から settled への変更のみ対応しています")
    updated_count, ids = store.bulk_status(payload.from_, payload.to, UUID(user["id"]))
    store.write_audit(
        "ticket_bulk_status_update",
        "ticket",
        user["id"],
        before={"from": payload.from_.isoformat(), "to": payload.to.isoformat(), "from_status": payload.from_status},
        after={"to_status": payload.to_status, "updated_count": updated_count, "ticket_ids": ids},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"updated_count": updated_count, "to_status": "settled"}


@router.post("/bulk-tags", response_model=BulkTagsResponse)
def bulk_add_tags(payload: BulkTagsRequest, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    try:
        updated_count, ids = store.bulk_add_tags(
            [str(value) for value in payload.ticket_ids],
            [str(value) for value in payload.tag_ids],
            UUID(user["id"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    store.write_audit(
        "ticket_bulk_tag_add",
        "ticket",
        user["id"],
        after={"tag_ids": [str(value) for value in payload.tag_ids], "updated_count": updated_count, "ticket_ids": ids},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"updated_count": updated_count, "ticket_ids": ids}


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: UUID, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    ticket = store.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="チケットが見つかりません")
    return ticket


@router.put("/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: UUID, payload: TicketUpdate, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    try:
        before, ticket = store.update_ticket(ticket_id, payload, UUID(user["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=404, detail="チケットが見つかりません")
    store.write_audit(
        "ticket_update",
        "ticket",
        user["id"],
        ticket["id"],
        before=before,
        after=store.ticket_audit_dict(ticket),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ticket


@router.delete("/{ticket_id}")
def delete_ticket(ticket_id: UUID, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    try:
        before, after = store.delete_ticket(ticket_id, UUID(user["id"]))
    except KeyError:
        raise HTTPException(status_code=404, detail="チケットが見つかりません")
    store.write_audit(
        "ticket_delete",
        "ticket",
        user["id"],
        ticket_id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"ok": True}
