from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.routers.deps import current_user
from app.schemas.auth import UserOut, UserUpdate
from app.store import DynamoStore, get_store

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def users(store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    return store.list_users()


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: UUID, payload: UserUpdate, request: Request, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="表示名を入力してください")
    try:
        before, target = store.update_user_name(user_id, name)
    except KeyError:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    store.write_audit(
        "setting_update_user_name",
        "user",
        user["id"],
        target["id"],
        before=before,
        after={"name": target["name"]},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return target
