from fastapi import APIRouter, Depends

from app.routers.deps import current_user
from app.schemas.audit import AuditLogOut
from app.store import DynamoStore, get_store

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(limit: int = 100, store: DynamoStore = Depends(get_store), user: dict = Depends(current_user)):
    return store.list_audit_logs(limit)
