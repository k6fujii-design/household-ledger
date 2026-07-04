from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.routers.deps import current_user
from app.schemas.auth import AuthResponse, LoginRequest
from app.store import DynamoStore, get_store

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, store: DynamoStore = Depends(get_store)):
    user = store.authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="メールアドレスまたはパスワードが違います")
    request.session["user_id"] = user["id"]
    return {"user": user}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me", response_model=AuthResponse)
def me(user: dict = Depends(current_user)):
    return {"user": user}
