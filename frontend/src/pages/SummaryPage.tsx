import { CheckCheck, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AppSettings, Category, MonthlySettlement, Summary, User } from "../types";
import { formatYen, userPair } from "../utils/display";
import { currentPeriod } from "../utils/period";

export function SummaryPage({ users, categories, settings }: { users: User[]; categories: Category[]; settings: AppSettings }) {
  const initial = currentPeriod(settings.closing_day);
  const [from, setFrom] = useState(initial.from);
  const [to, setTo] = useState(initial.to);
  const [category, setCategory] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [monthly, setMonthly] = useState<MonthlySettlement | null>(null);
  const [message, setMessage] = useState("");
  const pair = userPair(users);
  const periodKey = to.slice(0, 7);

  async function load() {
    setSummary(await api.summary(from, to, "new,settled", category));
    const row = await api.monthlySettlement(periodKey);
    setMonthly({ ...row, status: row.status === "settled" ? "settled" : "new" });
  }

  useEffect(() => {
    load();
  }, []);

  async function bulk() {
    if (!confirm("対象期間の未精算チケットを精算済みに変更します。\nこの操作を実行しますか？")) return;
    const result = await api.bulkStatus(from, to);
    setMessage(`${result.updated_count}件のチケットを精算済みに変更しました。`);
    await load();
  }

  async function saveMonthly() {
    if (!monthly) return;
    const saved = await api.updateMonthlySettlement(periodKey, {
      status: monthly.status === "settled" ? "settled" : "new",
      memo: monthly.memo,
      closing_day: settings.closing_day
    });
    setMonthly({ ...saved, status: saved.status === "settled" ? "settled" : "new" });
    setMessage("月次メモを保存しました。");
  }

  return (
    <main className="screen">
      <header className="top"><h1>集計</h1><button onClick={load}>更新</button></header>
      <section className="filters compact-filters">
        <label>表示開始日<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label>表示終了日<input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        <label>カテゴリ<select value={category} onChange={(e) => setCategory(e.target.value)}><option value="">全カテゴリ</option>{categories.map((row) => <option key={row.id} value={row.name}>{row.name}</option>)}</select></label>
        <button onClick={load}>集計</button>
      </section>
      {monthly && (
        <section className="monthly-panel">
          <div><strong>{periodKey} 月次メモ</strong><span className="muted">締め日: {settings.closing_day}日</span></div>
          <select value={monthly.status} onChange={(e) => setMonthly({ ...monthly, status: e.target.value })}>
            <option value="new">未精算</option>
            <option value="settled">精算済み</option>
          </select>
          <textarea value={monthly.memo} onChange={(e) => setMonthly({ ...monthly, memo: e.target.value })} placeholder="自由メモ" />
          <button onClick={saveMonthly}><Save size={18} />保存</button>
        </section>
      )}
      {summary && <section className="metrics">
        <div><span>対象件数</span><strong>{summary.ticket_count}件</strong></div>
        <div><span>合計</span><strong>{formatYen(summary.total_amount)}</strong></div>
        <div><span>{pair.first} 支払 / 負担</span><strong>{formatYen(summary.paid_by_f)} / {formatYen(summary.share_f)}</strong></div>
        <div><span>{pair.second} 支払 / 負担</span><strong>{formatYen(summary.paid_by_o)} / {formatYen(summary.share_o)}</strong></div>
        <div><span>精算</span><strong>{summary.settlement.amount ? `${summary.settlement.from_user} → ${summary.settlement.to_user} ${formatYen(summary.settlement.amount)}` : "不要"}</strong></div>
      </section>}
      <button className="wide" onClick={bulk}><CheckCheck size={18} />対象チケットを精算済みにする</button>
      {message && <div className="success">{message}</div>}
    </main>
  );
}
