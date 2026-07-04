from datetime import date
from pydantic import BaseModel


class Settlement(BaseModel):
    from_user: str | None
    to_user: str | None
    amount: int


class SummaryResponse(BaseModel):
    from_: date
    to: date
    total_amount: int
    ticket_count: int
    paid_by_f: int
    paid_by_o: int
    share_f: int
    share_o: int
    balance_f: int
    balance_o: int
    settlement: Settlement

    model_config = {"populate_by_name": True}
