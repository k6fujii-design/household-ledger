from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from app.store import DynamoStore, get_store


def current_user(request: Request, store: DynamoStore = Depends(get_store)) -> dict:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ログインしてください")
    user = store.get_user(UUID(user_id))
    if not user:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ログインしてください")
    return user
