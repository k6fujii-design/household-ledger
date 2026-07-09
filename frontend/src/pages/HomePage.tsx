import type { CSSProperties } from "react";
import { AlertCircle, CheckCircle2, ChevronLeft, ChevronRight, MinusCircle, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { ShareBar } from "../components/ShareBar";
import { StatusBadge } from "../components/StatusBadge";
import type { AppSettings, Category, Summary, Ticket, User } from "../types";
import type { View } from "../App";
import { formatYen } from "../utils/display";
import { addMonths, currentPeriod, monthLabel } from "../utils/period";
import { swipeDirection, type TouchPoint } from "../utils/swipe";

function weekdayLabel(date: string) {
  return new Date(`${date}T00:00:00`).toLocaleDateString("ja-JP", { month: "numeric", day: "numeric", weekday: "short" });
}

export function HomePage({ users, categories, settings, setView, openEdit }: { users: User[]; categories: Category[]; settings: AppSettings; setView: (view: View) => void; openEdit: (id: string) => void }) {
  const [baseMonth, setBaseMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [summary, setSummary] = useState<Summary | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [touchStart, setTouchStart] = useState<TouchPoint | null>(null);
  const period = currentPeriod(settings.closing_day, baseMonth);

  async function load() {
    const [summaryRow, ticketRows] = await Promise.all([
      api.summary(period.from, period.to, "new,settled,canceled"),
      api.tickets(`?from=${period.from}&to=${period.to}`)
    ]);
    setSummary(summaryRow);
    setTickets(ticketRows.sort((a, b) => b.date.localeCompare(a.date) || b.updated_at.localeCompare(a.updated_at)));
  }

  useEffect(() => {
    load();
  }, [period.from, period.to]);

  const grouped = useMemo(() => {
    const rows: { date: string; total: number; tickets: Ticket[] }[] = [];
    for (const ticket of tickets) {
      const current = rows.find((row) => row.date === ticket.date);
      if (current) {
        current.tickets.push(ticket);
        current.total += ticket.amount;
      } else {
        rows.push({ date: ticket.date, total: ticket.amount, tickets: [ticket] });
      }
    }
    return rows;
  }, [tickets]);

  const settlementState = useMemo(() => {
    if (tickets.some((ticket) => ticket.status === "new")) {
      return { label: "未精算あり", className: "open", Icon: AlertCircle };
    }
    if (!summary?.settlement.amount) {
      return { label: "精算不要", className: "none", Icon: MinusCircle };
    }
    return { label: "精算済み", className: "settled", Icon: CheckCircle2 };
  }, [summary?.settlement.amount, tickets]);

  function categoryColor(name: string) {
    if (!name) return "#9aa3a8";
    return categories.find((category) => category.name === name)?.color || "#ffd166";
  }

  function move(diff: number) {
    setBaseMonth(addMonths(baseMonth, diff));
  }

  function handleTouchEnd(point: TouchPoint) {
    const direction = swipeDirection(touchStart, point);
    if (direction) move(direction);
    setTouchStart(null);
  }

  const StatusIcon = settlementState.Icon;

  return (
    <main className="screen ledger-screen" onTouchStart={(e) => setTouchStart({ x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY })} onTouchEnd={(e) => handleTouchEnd({ x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY })}>
      <header className="month-switch">
        <button className="ghost-icon" onClick={() => move(-1)} aria-label="前月"><ChevronLeft /></button>
        <strong>{monthLabel(baseMonth)}</strong>
        <button className="ghost-icon" onClick={() => move(1)} aria-label="翌月"><ChevronRight /></button>
      </header>

      <section className="settlement-hero">
        <div className={`settlement-status ${settlementState.className}`}>
          <StatusIcon size={18} />
          {settlementState.label}
        </div>
        <div className="settlement-route">{summary?.settlement.amount ? `${summary.settlement.from_user} → ${summary.settlement.to_user}` : "精算不要"}</div>
        <strong>{formatYen(summary?.settlement.amount || 0)}</strong>
      </section>

      <section className="timeline">
        {grouped.map((group) => (
          <article key={group.date} className="timeline-day">
            <div className="timeline-date">
              <span>{weekdayLabel(group.date)}</span>
              <strong>支出 {formatYen(group.total)}</strong>
            </div>
            <div className="timeline-tickets">
              {group.tickets.map((ticket) => (
                <button key={ticket.id} className="ledger-ticket" style={{ "--category-color": categoryColor(ticket.category) } as CSSProperties} onClick={() => openEdit(ticket.id)}>
                  <div>
                    <strong>{ticket.title}</strong>
                    <span className="ledger-ticket-meta">
                      <span><i className="category-dot" />{ticket.category || "未指定"}</span>
                      <StatusBadge status={ticket.status} />
                    </span>
                  </div>
                  <b>{formatYen(ticket.amount)}</b>
                  <ShareBar users={users} ratioF={ticket.ratio_f} ratioO={ticket.ratio_o} amountF={ticket.share_f} amountO={ticket.share_o} compact percent />
                </button>
              ))}
            </div>
          </article>
        ))}
        {grouped.length === 0 && <div className="empty-state">この月のチケットはありません。</div>}
      </section>

      <button className="ticket-list-link" onClick={() => setView("tickets")}>チケット一覧を見る</button>
      <button className="fab" onClick={() => setView("create")} aria-label="記録を追加"><Plus size={28} /></button>
    </main>
  );
}
