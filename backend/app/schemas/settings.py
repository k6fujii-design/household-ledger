from uuid import UUID

from pydantic import BaseModel, Field


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = "#ff8f70"


class CategoryOut(CategoryIn):
    id: UUID
    description: str = ""
    icon: str = "tag"
    is_default: bool = False

    model_config = {"from_attributes": True}


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    amount: int = Field(ge=1)
    payer_user_id: UUID | None = None
    ratio_f: int = Field(ge=0)
    ratio_o: int = Field(ge=0)
    status: str = "new"
    category: str = ""
    memo: str = ""


class TemplateOut(TemplateIn):
    id: UUID

    model_config = {"from_attributes": True}


class AppSettingsOut(BaseModel):
    closing_day: int


class AppSettingsIn(BaseModel):
    closing_day: int = Field(ge=1, le=31)


class MonthlySettlementIn(BaseModel):
    status: str = "open"
    memo: str = ""
    closing_day: int = Field(ge=1, le=31)


class MonthlySettlementOut(MonthlySettlementIn):
    period_key: str

    model_config = {"from_attributes": True}
