import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { BrandMark } from "../components/BrandMark";
import { TicketCard } from "../components/TicketCard";
import type { AppSettings, Summary, Ticket, User } from "../types";
import type { View } from "../App";
import { formatYen, userPair } from "../utils/display";
import { currentPeriod } from "../utils/period";

export function HomePage({ users, settings, setView, openEdit }: { users: User[]; settings: AppSettings; setView: (view: View) => void; openEdit: (id: string) => void }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const pair = userPair(users);
  const period = currentPeriod(settings.closing_day);

  useEffect(() => {
    api.summary(period.from, period.to).then(setSummary);
    api.tickets(`?from=${period.from}&to=${period.to}`).then((rows) => setTickets(rows.slice(0, 5)));
  }, [settings.closing_day]);

  return (
    <main className="screen">
      <header className="top hero-top">
        <div>
          <BrandMark />
          <h1>今月の共有メモ</h1>
          <div className="muted">{period.from} - {period.to}</div>
        </div>
        <button onClick={() => setView("create")}><Plus size={18} />追加</button>
      </header>
      <section className="metrics home-metrics">
        <div><span>合計</span><strong>{formatYen(summary?.total_amount || 0)}</strong></div>
        <div><span>精算</span><strong>{summary?.settlement.amount ? `${summary.settlement.from_user} → ${summary.settlement.to_user} ${formatYen(summary.settlement.amount)}` : "不要"}</strong></div>
        <div><span>{pair.first} 支払い</span><strong>{formatYen(summary?.paid_by_f || 0)}</strong></div>
        <div><span>{pair.second} 支払い</span><strong>{formatYen(summary?.paid_by_o || 0)}</strong></div>
      </section>
      <h2>最近のチケット</h2>
      <div className="list">{tickets.map((t) => <TicketCard key={t.id} users={users} ticket={t} onClick={() => openEdit(t.id)} />)}</div>
    </main>
  );
}
