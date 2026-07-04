from datetime import date
from pydantic import BaseModel


class CalendarDay(BaseModel):
    date: date
    total_amount: int
    ticket_count: int
    paid_by_f: int
    paid_by_o: int


class CalendarMonthResponse(BaseModel):
    year: int
    month: int
    days: list[CalendarDay]


class CalendarYearMonth(BaseModel):
    month: int
    total_amount: int
    ticket_count: int
    paid_by_f: int
    paid_by_o: int


class CalendarYearResponse(BaseModel):
    year: int
    months: list[CalendarYearMonth]
