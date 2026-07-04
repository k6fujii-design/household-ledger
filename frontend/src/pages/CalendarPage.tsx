import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { CalendarDay, CalendarMonthSummary, Category, Ticket, TicketStatus, User } from "../types";
import { compactYen, formatYen, userPair } from "../utils/display";

type CalendarFilter = "all" | TicketStatus;
type CalendarMode = "month" | "year";

const statusParam: Record<CalendarFilter, string> = {
  all: "new,settled,canceled",
  new: "new",
  settled: "settled",
  canceled: "canceled"
};

const statusLabel: Record<CalendarFilter, string> = {
  all: "すべて",
  new: "未精算",
  settled: "精算済み",
  canceled: "取り消し"
};

const weekdays = ["日", "月", "火", "水", "木", "金", "土"];

export function CalendarPage({ users, categories, openEdit }: { users: User[]; categories: Category[]; openEdit: (id: string) => void }) {
  const today = new Date();
  const [mode, setMode] = useState<CalendarMode>("month");
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [filter, setFilter] = useState<CalendarFilter>("all");
  const [category, setCategory] = useState("");
  const [days, setDays] = useState<CalendarDay[]>([]);
  const [yearMonths, setYearMonths] = useState<CalendarMonthSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [touchStartX, setTouchStartX] = useState<number | null>(null);
  const pair = userPair(users);
  const dayMap = useMemo(() => Object.fromEntries(days.map((d) => [d.date, d])), [days]);
  const visibleTotal = useMemo(() => {
    if (mode === "year") return yearMonths.reduce((sum, item) => sum + item.total_amount, 0);
    return days.reduce((sum, day) => sum + day.total_amount, 0);
  }, [days, mode, yearMonths]);

  async function loadMonth() {
    const res = await api.calendar(year, month, statusParam[filter], category);
    setDays(res.days);
  }

  async function loadYear() {
    const res = await api.calendarYear(year, statusParam[filter], category);
    setYearMonths(res.months);
  }

  useEffect(() => {
    if (mode === "year") loadYear();
    else loadMonth();
  }, [year, month, filter, category, mode]);

  async function pick(date: string) {
    setSelected(date);
    if (filter === "all") {
      const rows = await Promise.all(["new", "settled", "canceled"].map((status) => {
        const params = new URLSearchParams({ from: date, to: date, status });
        if (category) params.set("category", category);
        return api.tickets(`?${params.toString()}`);
      }));
      setTickets(rows.flat());
      return;
    }
    const params = new URLSearchParams({ from: date, to: date, status: filter });
    if (category) params.set("category", category);
    setTickets(await api.tickets(`?${params.toString()}`));
  }

  useEffect(() => {
    if (selected && mode === "month") pick(selected);
  }, [filter, category]);

  function move(diff: number) {
    if (mode === "year") setYear(year + diff);
    else {
      const d = new Date(year, month - 1 + diff, 1);
      setYear(d.getFullYear());
      setMonth(d.getMonth() + 1);
    }
    setSelected(null);
  }

  function handleTouchEnd(x: number) {
    if (mode !== "month" || touchStartX === null) return;
    const delta = x - touchStartX;
    if (Math.abs(delta) > 50) move(delta > 0 ? -1 : 1);
    setTouchStartX(null);
  }

  function openMonth(targetMonth: number) {
    setMonth(targetMonth);
    setMode("month");
    setSelected(null);
  }

  const firstWeekday = new Date(year, month - 1, 1).getDay();
  const cells = [
    ...Array.from({ length: firstWeekday }, () => ""),
    ...Array.from({ length: new Date(year, month, 0).getDate() }, (_, i) => `${year}-${String(month).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`)
  ];

  return (
    <main className="screen" onTouchStart={(e) => setTouchStartX(e.changedTouches[0].clientX)} onTouchEnd={(e) => handleTouchEnd(e.changedTouches[0].clientX)}>
      <header className="month-head">
        <button onClick={() => move(-1)} aria-label={mode === "year" ? "前年" : "前月"}><ChevronLeft /></button>
        <h1>{mode === "year" ? `${year}年` : `${year}年${month}月`}</h1>
        <button onClick={() => move(1)} aria-label={mode === "year" ? "翌年" : "翌月"}><ChevronRight /></button>
      </header>
      <div className="segmented">
        <button className={mode === "month" ? "on" : ""} onClick={() => setMode("month")}>月次</button>
        <button className={mode === "year" ? "on" : ""} onClick={() => { setMode("year"); setSelected(null); }}>年次</button>
      </div>
      <section className="calendar-summary">
        <span>{mode === "year" ? "年次表示合計" : "月次表示合計"}</span>
        <strong>{formatYen(visibleTotal)}</strong>
      </section>
      <div className="segmented">
        {(Object.keys(statusLabel) as CalendarFilter[]).map((key) => <button key={key} className={filter === key ? "on" : ""} onClick={() => setFilter(key)}>{statusLabel[key]}</button>)}
      </div>
      <select className="calendar-category" value={category} onChange={(e) => setCategory(e.target.value)}>
        <option value="">全カテゴリ</option>
        {categories.map((row) => <option key={row.id} value={row.name}>{row.name}</option>)}
      </select>

      {mode === "year" ? (
        <div className="year-grid">
          {yearMonths.map((item) => (
            <button key={item.month} className="month-card" onClick={() => openMonth(item.month)}>
              <strong>{item.month}月</strong>
              <span>{compactYen(item.total_amount)}</span>
              <small>{item.ticket_count}件</small>
              <small>{pair.first}: {compactYen(item.paid_by_f)}</small>
              <small>{pair.second}: {compactYen(item.paid_by_o)}</small>
            </button>
          ))}
        </div>
      ) : (
        <>
          <div className="weekday-grid">{weekdays.map((day, index) => <div key={day} className={index === 0 ? "sun" : index === 6 ? "sat" : ""}>{day}</div>)}</div>
          <div className="calendar-grid calendar-grid-open">{cells.map((date, index) => {
            if (!date) return <div key={`blank-${index}`} className="day blank" />;
            const d = dayMap[date];
            const weekday = new Date(date).getDay();
            const weekendClass = weekday === 0 ? " sunday" : weekday === 6 ? " saturday" : "";
            return (
              <button key={date} onClick={() => pick(date)} className={`${selected === date ? "day selected" : "day"}${weekendClass}`}>
                <strong>{Number(date.slice(-2))}</strong>
                {d && <>
                  <span className="day-total">{compactYen(d.total_amount)}</span>
                  <small>{d.ticket_count}件</small>
                  <small>{pair.first}: {compactYen(d.paid_by_f)}</small>
                  <small>{pair.second}: {compactYen(d.paid_by_o)}</small>
                </>}
              </button>
            );
          })}</div>
          {selected && <><h2>{selected}</h2><div className="list">{tickets.map((t) => <button className="mini-ticket" key={t.id} onClick={() => openEdit(t.id)}>{t.title}<span>{formatYen(t.amount)}</span></button>)}</div></>}
        </>
      )}
    </main>
  );
}
