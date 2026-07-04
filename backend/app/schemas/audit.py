from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    actor_name: str | None = None
    action: str
    target_type: str
    target_id: UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
