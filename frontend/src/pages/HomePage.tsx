import type { CSSProperties } from "react";
import { AlertCircle, CheckCheck, CheckCircle2, ChevronLeft, ChevronRight, MinusCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { ShareBar } from "../components/ShareBar";
import { StatusBadge } from "../components/StatusBadge";
import { CategoryIcon, categoryForName } from "../components/CategoryIcon";
import type { AppSettings, Category, Summary, Ticket, User } from "../types";
import type { View } from "../App";
import { formatYen } from "../utils/display";
import { addMonths, currentPeriod, monthLabel } from "../utils/period";
import { swipeDirection, type TouchPoint } from "../utils/swipe";

function weekdayLabel(date: string) {
  return new Date(`${date}T00:00:00`).toLocaleDateString("ja-JP", { month: "numeric", day: "numeric", weekday: "short" });
}

export function HomePage({
  users,
  categories,
  settings,
  setView,
  openDetail
}: {
  users: User[];
  categories: Category[];
  settings: AppSettings;
  setView: (view: View) => void;
  openDetail: (id: string) => void;
}) {
  const [baseMonth, setBaseMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [unpaidSummary, setUnpaidSummary] = useState<Summary | null>(null);
  const [touchStart, setTouchStart] = useState<TouchPoint | null>(null);
  const period = currentPeriod(settings.closing_day, baseMonth);

  async function load() {
    const [ticketRows, summaryRow] = await Promise.all([
      api.tickets(`?from=${period.from}&to=${period.to}`),
      api.summary(period.from, period.to, "new")
    ]);
    setTickets(ticketRows.sort((a, b) => b.date.localeCompare(a.date) || b.updated_at.localeCompare(a.updated_at)));
    setUnpaidSummary(summaryRow);
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

  const paymentTotals = useMemo(() => {
    return tickets.reduce(
      (sum, ticket) => {
        if (ticket.status === "new") {
          sum.unpaid += ticket.amount;
          sum.unpaidCount += 1;
        }
        if (ticket.status === "settled") {
          sum.settled += ticket.amount;
          sum.settledCount += 1;
        }
        return sum;
      },
      { unpaid: 0, settled: 0, unpaidCount: 0, settledCount: 0 }
    );
  }, [tickets]);

  const settlementState = useMemo(() => {
    if (paymentTotals.unpaidCount > 0) {
      return { label: "未精算あり", className: "open", Icon: AlertCircle };
    }
    if (paymentTotals.unpaid + paymentTotals.settled === 0) {
      return { label: "精算不要", className: "none", Icon: MinusCircle };
    }
    return { label: "精算済み", className: "settled", Icon: CheckCircle2 };
  }, [paymentTotals]);

  const unpaidSettlement = unpaidSummary?.settlement;
  const settlementAmount = unpaidSettlement?.amount || 0;
  const hasSettlement = settlementAmount > 0 && unpaidSettlement?.from_user && unpaidSettlement?.to_user;

  function categoryColor(name: string) {
    if (!name) return "#9aa3a8";
    return categories.find((category) => category.name === name)?.color || "#ffd166";
  }

  function payerName(ticket: Ticket) {
    return ticket.payer_name || users.find((user) => user.id === ticket.payer_user_id)?.name || "不明";
  }

  function move(diff: number) {
    setBaseMonth(addMonths(baseMonth, diff));
  }

  function handleTouchEnd(point: TouchPoint) {
    const direction = swipeDirection(touchStart, point);
    if (direction) move(direction);
    setTouchStart(null);
  }

  async function bulkSettle() {
    if (!paymentTotals.unpaidCount) return;
    if (!confirm(`${monthLabel(baseMonth)} の未精算チケット ${paymentTotals.unpaidCount}件を精算済みにします。よろしいですか？`)) return;
    await api.bulkStatus(period.from, period.to);
    await load();
  }

  const StatusIcon = settlementState.Icon;

  return (
    <main
      className="screen ledger-screen"
      onTouchStart={(e) => setTouchStart({ x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY })}
      onTouchEnd={(e) => handleTouchEnd({ x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY })}
    >
      <header className="month-switch">
        <button className="ghost-icon" onClick={() => move(-1)} aria-label="前月"><ChevronLeft /></button>
        <strong>{monthLabel(baseMonth)}</strong>
        <button className="ghost-icon" onClick={() => move(1)} aria-label="翌月"><ChevronRight /></button>
      </header>

      <section className="settlement-hero settlement-dashboard">
        <div className={`settlement-status ${settlementState.className}`}>
          <StatusIcon size={18} />
          {settlementState.label}
        </div>

        <article className={`settlement-transfer-card ${hasSettlement ? "open" : "none"}`}>
          <span>あと支払う金額</span>
          {hasSettlement ? (
            <>
              <strong>{formatYen(settlementAmount)}</strong>
              <small>{unpaidSettlement.from_user} から {unpaidSettlement.to_user} へ</small>
            </>
          ) : (
            <>
              <strong>{formatYen(0)}</strong>
              <small>{paymentTotals.unpaidCount ? "未精算分の支払い調整は不要です" : "未精算チケットはありません"}</small>
            </>
          )}
        </article>

        <div className="settlement-total-grid">
          <article className="settlement-total-card open">
            <span>未精算</span>
            <strong>{formatYen(paymentTotals.unpaid)}</strong>
            <small>{paymentTotals.unpaidCount}件</small>
          </article>
          <article className="settlement-total-card settled">
            <span>精算済み</span>
            <strong>{formatYen(paymentTotals.settled)}</strong>
            <small>{paymentTotals.settledCount}件</small>
          </article>
        </div>
        <button className="home-bulk-button" onClick={bulkSettle} disabled={!paymentTotals.unpaidCount}>
          <CheckCheck size={18} />
          未精算を一括精算
        </button>
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
                <button key={ticket.id} className="ledger-ticket" style={{ "--category-color": categoryColor(ticket.category) } as CSSProperties} onClick={() => openDetail(ticket.id)}>
                  <div>
                    <strong>{ticket.title}</strong>
                    <span className="ledger-ticket-meta">
                      <span><CategoryIcon category={categoryForName(categories, ticket.category || "その他")} size={15} />{ticket.category || "その他"}</span>
                      <span className="payer-chip">立替: {payerName(ticket)}</span>
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
    </main>
  );
}
