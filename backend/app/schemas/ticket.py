from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

VALID_STATUSES = {"new", "settled", "canceled"}


class TicketBase(BaseModel):
    date: date
    title: str = Field(min_length=1, max_length=160)
    amount: int = Field(ge=1)
    payer_user_id: UUID
    ratio_f: int = Field(ge=0)
    ratio_o: int = Field(ge=0)
    status: str = "new"
    category: str = ""
    memo: str = ""
    tag_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in VALID_STATUSES:
            raise ValueError("status must be new, settled, or canceled")
        return value

    @field_validator("ratio_o")
    @classmethod
    def ratio_not_zero(cls, value: int, info):
        ratio_f = info.data.get("ratio_f", 0)
        if ratio_f == 0 and value == 0:
            raise ValueError("ratio_f and ratio_o cannot both be zero")
        return value


class TicketCreate(TicketBase):
    @model_validator(mode="after")
    def valid_share_total(self):
        if self.ratio_f + self.ratio_o != 10:
            raise ValueError("負担比率の合計は10（100%）にしてください")
        return self


class TicketUpdate(TicketCreate):
    pass


class TicketOut(TicketBase):
    id: UUID
    display_id: int
    share_f: int
    share_o: int
    created_by: UUID
    updated_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    payer_name: str | None = None

    model_config = {"from_attributes": True}


class BulkStatusRequest(BaseModel):
    from_: date = Field(alias="from")
    to: date
    from_status: str = "new"
    to_status: str = "settled"


class BulkStatusResponse(BaseModel):
    updated_count: int
    to_status: str


class BulkTagsRequest(BaseModel):
    ticket_ids: list[UUID] = Field(min_length=1, max_length=200)
    tag_ids: list[UUID] = Field(min_length=1, max_length=20)


class BulkTagsResponse(BaseModel):
    updated_count: int
    ticket_ids: list[UUID]
