import { ChevronLeft, ChevronRight, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { CalendarDay, Category, Tag, Ticket, TicketStatus, User } from "../types";
import { compactYen, formatYen } from "../utils/display";
import { swipeDirection, type TouchPoint } from "../utils/swipe";

type CalendarFilter = "all" | TicketStatus;

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

export function CalendarPage({
  categories,
  openEdit,
  openCreate
}: {
  users: User[];
  categories: Category[];
  openEdit: (id: string) => void;
  openCreate: (date: string) => void;
}) {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [filter, setFilter] = useState<CalendarFilter>("all");
  const [category, setCategory] = useState("");
  const [tags, setTags] = useState<Tag[]>([]);
  const [tagId, setTagId] = useState("");
  const [error, setError] = useState("");
  const [days, setDays] = useState<CalendarDay[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [touchStart, setTouchStart] = useState<TouchPoint | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const dayMap = useMemo(() => Object.fromEntries(days.map((d) => [d.date, d])), [days]);
  const visibleTotal = useMemo(() => days.reduce((sum, day) => sum + day.total_amount, 0), [days]);

  useEffect(() => {
    api.tags().then(setTags).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    let active = true;
    setDays([]);
    setError("");
    api.calendar(year, month, statusParam[filter], category, tagId)
      .then((res) => { if (active) setDays(res.days); })
      .catch((e) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [year, month, filter, category, tagId]);

  async function selectDate(date: string) {
    setSelected(date);
    if (confirm(`${date} のチケットを新規作成しますか？`)) {
      openCreate(date);
    }
  }

  useEffect(() => {
    let active = true;
    setTickets([]);
    if (selected) {
      const statuses = filter === "all" ? ["new", "settled", "canceled"] : [filter];
      Promise.all(statuses.map((status) => {
        const params = new URLSearchParams({ from: selected, to: selected, status });
        if (category) params.set("category", category);
        if (tagId) params.set("tag_id", tagId);
        return api.tickets(`?${params.toString()}`);
      })).then((rows) => { if (active) setTickets(rows.flat()); })
        .catch((e) => { if (active) setError(e.message); });
    }
    return () => { active = false; };
  }, [selected, filter, category, tagId]);

  function move(diff: number) {
    const d = new Date(year, month - 1 + diff, 1);
    setYear(d.getFullYear());
    setMonth(d.getMonth() + 1);
    setSelected(null);
  }

  function handleTouchEnd(point: TouchPoint) {
    const direction = swipeDirection(touchStart, point);
    if (direction) move(direction);
    setTouchStart(null);
  }

  const firstWeekday = new Date(year, month - 1, 1).getDay();
  const cells = [
    ...Array.from({ length: firstWeekday }, () => ""),
    ...Array.from({ length: new Date(year, month, 0).getDate() }, (_, i) => `${year}-${String(month).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`)
  ];

  return (
    <main className="screen" onTouchStart={(e) => setTouchStart({ x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY })} onTouchEnd={(e) => handleTouchEnd({ x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY })}>
      <header className="month-head">
        <button onClick={() => move(-1)} aria-label="前月"><ChevronLeft /></button>
        <h1>{year}年{month}月</h1>
        <button onClick={() => move(1)} aria-label="翌月"><ChevronRight /></button>
      </header>
      <button className="secondary filter-toggle" onClick={() => setShowFilters(!showFilters)}><SlidersHorizontal size={18} />フィルター</button>
      {showFilters && <section className="calendar-filter-panel">
        <div className="segmented">
          {(Object.keys(statusLabel) as CalendarFilter[]).map((key) => <button key={key} className={filter === key ? "on" : ""} onClick={() => setFilter(key)}>{statusLabel[key]}</button>)}
        </div>
        <select className="calendar-category" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">全カテゴリ</option>
          {categories.map((row) => <option key={row.id} value={row.name}>{row.name}</option>)}
        </select>
        <label>タグ<select className="calendar-category" value={tagId} onChange={(e) => setTagId(e.target.value)}>
          <option value="">すべてのチケット</option>
          {tags.map((tag) => <option key={tag.id} value={tag.id}>#{tag.name}</option>)}
        </select></label>
      </section>}
      {error && <div className="error" role="alert">{error}</div>}
      <section className="calendar-summary">
        <span>月次表示合計</span>
        <strong>{formatYen(visibleTotal)}</strong>
      </section>

      <div className="weekday-grid">{weekdays.map((day, index) => <div key={day} className={index === 0 ? "sun" : index === 6 ? "sat" : ""}>{day}</div>)}</div>
      <div className="calendar-grid calendar-grid-open">{cells.map((date, index) => {
        if (!date) return <div key={`blank-${index}`} className="day blank" />;
        const d = dayMap[date];
        const weekday = new Date(date).getDay();
        const weekendClass = weekday === 0 ? " sunday" : weekday === 6 ? " saturday" : "";
        return (
          <button key={date} onClick={() => selectDate(date)} className={`${selected === date ? "day selected" : "day"}${weekendClass}`}>
            <strong>{Number(date.slice(-2))}</strong>
            {d && <>
              <span className="day-total">{compactYen(d.total_amount)}</span>
              <small>{d.ticket_count}件</small>
            </>}
          </button>
        );
      })}</div>
      {selected && <>
        <div className="selected-day-head">
          <h2>{selected}</h2>
          <button onClick={() => openCreate(selected)}>この日に作成</button>
        </div>
        <div className="list">{tickets.map((t) => <button className="mini-ticket" key={t.id} onClick={() => openEdit(t.id)}>{t.title}<span>{formatYen(t.amount)}</span></button>)}</div>
      </>}
    </main>
  );
}
