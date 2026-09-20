from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.routers.deps import current_user
from app.schemas.settings import (
    AppSettingsIn,
    AppSettingsOut,
    CategoryIn,
    CategoryOut,
    MonthlySettlementIn,
    MonthlySettlementOut,
    TemplateIn,
    TemplateOut,
)
from app.store import DynamoStore, get_store

router = APIRouter(prefix="/api/settings", tags=["settings"])


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    scope: Literal["personal", "shared"] = "personal"


@router.get("/tags")
def list_tags(store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    return store.list_tags()


@router.post("/tags")
def create_tag(payload: TagIn, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    try:
        row = store.save_tag(payload.name)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    store.write_audit("setting_create_tag", "tag", user["id"], row["id"], after={"name": row["name"]})
    return row


@router.put("/tags/{tag_id}")
def update_tag(tag_id: UUID, payload: TagIn, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    try:
        row = store.save_tag(payload.name, str(tag_id))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    store.write_audit("setting_update_tag", "tag", user["id"], tag_id, after={"name": row["name"]})
    return row


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: UUID, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    try:
        store.delete_tag(str(tag_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    store.write_audit("setting_delete_tag", "tag", user["id"], tag_id)
    return {"ok": True}


@router.get("/memories")
def list_memories(scope: Literal["personal", "shared"] = "personal", store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    return store.list_memories(user["id"], scope)


@router.post("/memories")
def create_memory(payload: MemoryIn, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    try:
        row = store.save_memory(user["id"], payload.content, payload.scope)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    store.write_audit("agent_memory_create", "memory", user["id"], row["id"], after={"scope": payload.scope})
    return row


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: UUID, scope: Literal["personal", "shared"] = "personal", store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    store.delete_memory(user["id"], str(memory_id), scope)
    store.write_audit("agent_memory_delete", "memory", user["id"], memory_id, before={"scope": scope})
    return {"ok": True}


def audit_context(request: Request) -> dict:
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


@router.get("", response_model=AppSettingsOut)
def read_settings(store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    return {"closing_day": store.get_closing_day()}


@router.put("", response_model=AppSettingsOut)
def update_settings(payload: AppSettingsIn, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    before, after = store.update_closing_day(payload.closing_day)
    store.write_audit("setting_update_closing_day", "setting", user["id"], before=before, after=after, **audit_context(request))
    return after


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    return store.list_categories()


@router.post("/categories", response_model=CategoryOut)
def create_category(payload: CategoryIn, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    row = store.create_category(payload.name, payload.color)
    store.write_audit("setting_create_category", "category", user["id"], row["id"], after={"name": row["name"], "color": row["color"]}, **audit_context(request))
    return row


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: UUID, payload: CategoryIn, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    try:
        before, row = store.update_category(category_id, payload.name, payload.color)
    except KeyError:
        raise HTTPException(status_code=404, detail="カテゴリが見つかりません")
    store.write_audit("setting_update_category", "category", user["id"], row["id"], before=before, after={"name": row["name"], "color": row["color"]}, **audit_context(request))
    return row


@router.delete("/categories/{category_id}")
def delete_category(category_id: UUID, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    row = store.delete_category(category_id)
    if row:
        store.write_audit("setting_delete_category", "category", user["id"], category_id, before={"name": row["name"], "color": row["color"]}, **audit_context(request))
    return {"ok": True}


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    return store.list_templates()


@router.post("/templates", response_model=TemplateOut)
def create_template(payload: TemplateIn, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    row = store.create_template(payload.model_dump(mode="json"))
    store.write_audit("setting_create_template", "template", user["id"], row["id"], after=payload.model_dump(mode="json"), **audit_context(request))
    return row


@router.put("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: UUID, payload: TemplateIn, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    try:
        before, row = store.update_template(template_id, payload.model_dump(mode="json"))
    except KeyError:
        raise HTTPException(status_code=404, detail="テンプレートが見つかりません")
    store.write_audit("setting_update_template", "template", user["id"], row["id"], before=before, after=payload.model_dump(mode="json"), **audit_context(request))
    return row


@router.delete("/templates/{template_id}")
def delete_template(template_id: UUID, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    row = store.delete_template(template_id)
    if row:
        before = {key: row.get(key) for key in ["name", "title", "amount", "payer_user_id", "ratio_f", "ratio_o", "status", "category", "memo"]}
        store.write_audit("setting_delete_template", "template", user["id"], template_id, before=before, **audit_context(request))
    return {"ok": True}


@router.get("/monthly-settlements/{period_key}", response_model=MonthlySettlementOut)
def get_monthly_settlement(period_key: str, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    return store.get_monthly_settlement(period_key)


@router.put("/monthly-settlements/{period_key}", response_model=MonthlySettlementOut)
def update_monthly_settlement(period_key: str, payload: MonthlySettlementIn, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    before, row = store.update_monthly_settlement(period_key, payload.model_dump(mode="json"))
    store.write_audit("setting_update_monthly_settlement", "monthly_settlement", user["id"], before=before, after=row, **audit_context(request))
    return row
