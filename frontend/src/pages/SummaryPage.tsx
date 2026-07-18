import { ChevronLeft, ChevronRight, Save } from "lucide-react";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { api } from "../api/client";
import { ShareBar } from "../components/ShareBar";
import { CategoryIcon, categoryForName } from "../components/CategoryIcon";
import type { AppSettings, Category, MonthlySettlement, Summary, Ticket, User } from "../types";
import { formatYen } from "../utils/display";
import { addMonths, currentPeriod, monthLabel } from "../utils/period";
import { swipeDirection, type TouchPoint } from "../utils/swipe";

type SummaryMode = "month" | "year";

const fallbackColors = ["#ef476f", "#ffd166", "#2ec4b6", "#8376ff", "#ff8f70", "#5fb0ff"];

function normalizeToTen(first: number, second: number) {
  const total = first + second;
  if (!total) return { first: 5, second: 5 };
  const normalizedFirst = Math.round((first / total) * 10 * 10) / 10;
  return { first: normalizedFirst, second: Math.round((10 - normalizedFirst) * 10) / 10 };
}

function CategorySummaryRow({
  row,
  users
}: {
  row: { name: string; amount: number; ratioF: number; ratioO: number; shareF: number; shareO: number; count: number; color: string; category?: Category };
  users: User[];
}) {
  const normalized = normalizeToTen(row.ratioF, row.ratioO);
  return (
    <article className="category-row">
      <div><CategoryIcon category={row.category} /><strong>{row.name}</strong><span>{row.count}件</span></div>
      <b>{formatYen(row.amount)}</b>
      <ShareBar users={users} ratioF={normalized.first} ratioO={normalized.second} amountF={row.shareF} amountO={row.shareO} compact percent />
    </article>
  );
}

export function SummaryPage({ users, categories, settings }: { users: User[]; categories: Category[]; settings: AppSettings }) {
  const [mode, setMode] = useState<SummaryMode>("month");
  const [baseMonth, setBaseMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [category, setCategory] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [monthly, setMonthly] = useState<MonthlySettlement | null>(null);
  const [message, setMessage] = useState("");
  const [touchStart, setTouchStart] = useState<TouchPoint | null>(null);

  const period = mode === "month"
    ? currentPeriod(settings.closing_day, baseMonth)
    : { from: `${baseMonth.getFullYear()}-01-01`, to: `${baseMonth.getFullYear()}-12-31`, key: `${baseMonth.getFullYear()}` };
  const periodKey = period.to.slice(0, 7);

  async function load() {
    const [summaryRow, ticketRows] = await Promise.all([
      api.summary(period.from, period.to, "new,settled", category),
      api.tickets(`?from=${period.from}&to=${period.to}${category ? `&category=${encodeURIComponent(category)}` : ""}`)
    ]);
    setSummary(summaryRow);
    setTickets(ticketRows.filter((ticket) => ticket.status !== "canceled"));
    if (mode === "month") {
      const row = await api.monthlySettlement(periodKey);
      setMonthly({ ...row, status: row.status === "settled" ? "settled" : "new" });
    } else {
      setMonthly(null);
    }
  }

  useEffect(() => {
    load();
  }, [period.from, period.to, category, mode]);

  const categoryRows = useMemo(() => {
    const map = new Map<string, { name: string; amount: number; ratioF: number; ratioO: number; shareF: number; shareO: number; count: number; color: string; category?: Category }>();
    for (const ticket of tickets) {
      const name = ticket.category || "その他";
      const categoryRow = categoryForName(categories, name);
      const color = ticket.category ? categoryRow?.color || fallbackColors[map.size % fallbackColors.length] : "#9aa3a8";
      const current = map.get(name) || { name, amount: 0, ratioF: 0, ratioO: 0, shareF: 0, shareO: 0, count: 0, color, category: categoryRow };
      current.amount += ticket.amount;
      current.ratioF += ticket.ratio_f;
      current.ratioO += ticket.ratio_o;
      current.shareF += ticket.share_f;
      current.shareO += ticket.share_o;
      current.count += 1;
      map.set(name, current);
    }
    return [...map.values()].sort((a, b) => b.amount - a.amount);
  }, [categories, tickets]);

  const pieStyle = useMemo(() => {
    const total = categoryRows.reduce((sum, row) => sum + row.amount, 0);
    if (!total) return { background: "#f4fbf7" };
    let cursor = 0;
    const stops = categoryRows.map((row) => {
      const start = cursor;
      cursor += (row.amount / total) * 100;
      return `${row.color} ${start}% ${cursor}%`;
    });
    return { background: `conic-gradient(${stops.join(", ")})` };
  }, [categoryRows]);

  const chartIcons = useMemo(() => {
    const total = categoryRows.reduce((sum, row) => sum + row.amount, 0);
    if (!total) return [];
    let cursor = 0;
    return categoryRows.flatMap((row) => {
      const share = row.amount / total;
      const middle = cursor + share / 2;
      cursor += share;
      if (share < 0.055) return [];
      const angle = middle * Math.PI * 2 - Math.PI / 2;
      return [{ ...row, left: 50 + Math.cos(angle) * 32, top: 50 + Math.sin(angle) * 32 }];
    }).slice(0, 7);
  }, [categoryRows]);

  const monthlyRows = useMemo(() => {
    const rows = Array.from({ length: 12 }, (_, index) => ({
      month: index + 1,
      amount: 0
    }));
    for (const ticket of tickets) {
      const month = Number(ticket.date.slice(5, 7));
      if (month >= 1 && month <= 12) rows[month - 1].amount += ticket.amount;
    }
    const max = Math.max(...rows.map((row) => row.amount), 1);
    return rows.map((row) => ({ ...row, percent: (row.amount / max) * 100 }));
  }, [tickets]);

  const totalRatio = summary ? normalizeToTen(summary.share_f, summary.share_o) : null;

  async function saveMonthly() {
    if (!monthly) return;
    const saved = await api.updateMonthlySettlement(periodKey, {
      status: monthly.status,
      memo: monthly.memo,
      closing_day: settings.closing_day
    });
    setMonthly({ ...saved, status: saved.status === "settled" ? "settled" : "new" });
    setMessage("月次メモを保存しました。");
  }

  function move(diff: number) {
    setBaseMonth(mode === "month" ? addMonths(baseMonth, diff) : new Date(baseMonth.getFullYear() + diff, 0, 1));
  }

  function handleTouchEnd(point: TouchPoint) {
    const direction = swipeDirection(touchStart, point);
    if (direction) move(direction);
    setTouchStart(null);
  }

  return (
    <main className="screen ledger-screen" onTouchStart={(e) => setTouchStart({ x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY })} onTouchEnd={(e) => handleTouchEnd({ x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY })}>
      <div className="summary-tabs">
        <button className={mode === "month" ? "on" : ""} onClick={() => setMode("month")}>月次</button>
        <button className={mode === "year" ? "on" : ""} onClick={() => setMode("year")}>年次</button>
      </div>
      <header className="month-switch">
        <button className="ghost-icon" onClick={() => move(-1)}><ChevronLeft /></button>
        <strong>{mode === "month" ? monthLabel(baseMonth) : `${baseMonth.getFullYear()}年`}</strong>
        <button className="ghost-icon" onClick={() => move(1)}><ChevronRight /></button>
      </header>
      <select className="calendar-category" value={category} onChange={(e) => setCategory(e.target.value)}>
        <option value="">全カテゴリ</option>
        {categories.map((row) => <option key={row.id} value={row.name}>{row.name}</option>)}
      </select>

      <section className="summary-visual summary-visual-premium">
        <div className="donut-wrap">
          <div className="donut" style={pieStyle}>
            <div className="donut-icons">
              {chartIcons.map((row) => (
                <span key={row.name} className="donut-icon-position" style={{ "--icon-left": `${row.left}%`, "--icon-top": `${row.top}%` } as CSSProperties}>
                  <CategoryIcon category={row.category} size={16} />
                </span>
              ))}
            </div>
          </div>
        </div>
        <div className="summary-total">
          <span>支出合計</span>
          <strong>{formatYen(summary?.total_amount || 0)}</strong>
          <div className="summary-counts"><small>チケット {summary?.ticket_count || 0}件</small><small>{categoryRows.length}カテゴリ</small></div>
        </div>
      </section>
      {totalRatio && <div className="summary-burden"><ShareBar users={users} ratioF={totalRatio.first} ratioO={totalRatio.second} amountF={summary?.share_f} amountO={summary?.share_o} percent /></div>}

      {mode === "year" && (
        <section className="year-bar-panel">
          {monthlyRows.map((row) => (
            <div key={row.month} className="month-bar-row">
              <span>{row.month}月</span>
              <div><i style={{ width: `${row.percent}%` }} /></div>
              <strong>{formatYen(row.amount)}</strong>
            </div>
          ))}
        </section>
      )}

      <section className="category-breakdown">
        {categoryRows.map((row) => (
          <CategorySummaryRow key={row.name} row={row} users={users} />
        ))}
        {categoryRows.length === 0 && <div className="empty-state">対象期間のチケットはありません。</div>}
      </section>

      {monthly && (
        <section className="monthly-panel note-panel">
          <div><strong>{periodKey} 月次メモ</strong><span className="muted">締め日: {settings.closing_day}日</span></div>
          <textarea value={monthly.memo} onChange={(e) => setMonthly({ ...monthly, memo: e.target.value })} placeholder="自由メモ" />
          <button onClick={saveMonthly}><Save size={18} />保存</button>
        </section>
      )}
      {message && <div className="success">{message}</div>}
    </main>
  );
}
