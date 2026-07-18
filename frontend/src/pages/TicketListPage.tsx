import { ArrowDownWideNarrow, ArrowUpNarrowWide, Filter, Plus, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { TicketCard } from "../components/TicketCard";
import type { Category, Ticket, User } from "../types";
import type { View } from "../App";

type SortMode = "date" | "amount_desc" | "amount_asc";

export function TicketListPage({ users, categories, setView, openDetail }: { users: User[]; categories: Category[]; setView: (view: View) => void; openDetail: (id: string) => void }) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [sort, setSort] = useState<SortMode>("date");

  async function load() {
    const params = new URLSearchParams();
    if (keyword) params.set("keyword", keyword);
    if (status) params.set("status", status);
    if (category) params.set("category", category);
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    setTickets(await api.tickets(`?${params.toString()}`));
  }

  const sortedTickets = useMemo(() => {
    const rows = [...tickets];
    if (sort === "amount_desc") return rows.sort((a, b) => b.amount - a.amount);
    if (sort === "amount_asc") return rows.sort((a, b) => a.amount - b.amount);
    return rows;
  }, [tickets, sort]);

  useEffect(() => {
    load();
  }, []);

  return (
    <main className="screen">
      <header className="top"><h1>チケット</h1><button onClick={() => setView("create")}><Plus size={18} />新規</button></header>
      <section className="ticket-search">
        <label><Search size={16} /><input placeholder="検索" value={keyword} onChange={(e) => setKeyword(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") load(); }} /></label>
        <button className="secondary" onClick={() => setShowFilters(!showFilters)}><Filter size={18} />検索バー</button>
      </section>
      {showFilters && (
        <section className="filters ticket-filters">
          <label>ステータス<select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">通常表示</option><option value="new">未精算</option><option value="settled">精算済み</option><option value="canceled">取り消し</option></select></label>
          <label>カテゴリ<select value={category} onChange={(e) => setCategory(e.target.value)}><option value="">全カテゴリ</option>{categories.map((row) => <option key={row.id} value={row.name}>{row.name}</option>)}</select></label>
          <label>表示開始日<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
          <label>表示終了日<input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
          <label>並び順<select value={sort} onChange={(e) => setSort(e.target.value as SortMode)}>
            <option value="date">日付順</option>
            <option value="amount_desc">金額が高い順</option>
            <option value="amount_asc">金額が低い順</option>
          </select></label>
          <button onClick={load}>絞り込み</button>
        </section>
      )}
      <div className="sort-note">
        {sort === "amount_desc" && <><ArrowDownWideNarrow size={16} />金額が高い順</>}
        {sort === "amount_asc" && <><ArrowUpNarrowWide size={16} />金額が低い順</>}
        {sort === "date" && "日付が新しい順"}
      </div>
      <div className="list">{sortedTickets.map((t) => <TicketCard key={t.id} users={users} categories={categories} ticket={t} onClick={() => openDetail(t.id)} />)}</div>
    </main>
  );
}
