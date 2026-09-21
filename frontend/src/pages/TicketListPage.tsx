import { ArrowDownWideNarrow, ArrowUpNarrowWide, Filter, Plus, Search, Tags } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { TicketCard } from "../components/TicketCard";
import { TagMultiSelect } from "../components/TagMultiSelect";
import type { Category, Tag, Ticket, User } from "../types";
import type { View } from "../App";

type SortMode = "date" | "amount_desc" | "amount_asc";

export function TicketListPage({ users, categories, setView, openDetail }: { users: User[]; categories: Category[]; setView: (view: View) => void; openDetail: (id: string) => void }) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [tagIds, setTagIds] = useState<string[]>([]);
  const [selectedTicketIds, setSelectedTicketIds] = useState<string[]>([]);
  const [bulkTagIds, setBulkTagIds] = useState<string[]>([]);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { api.tags().then(setTags).catch((e) => setError(e.message)); }, []);
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
    if (tagIds.length) params.set("tag_ids", tagIds.join(","));
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    setTickets(await api.tickets(`?${params.toString()}`));
    setSelectedTicketIds([]);
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

  function toggleTicket(ticketId: string) {
    setSelectedTicketIds((current) => current.includes(ticketId) ? current.filter((id) => id !== ticketId) : [...current, ticketId]);
  }

  async function applyTags() {
    if (!selectedTicketIds.length || !bulkTagIds.length) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await api.bulkAddTags(selectedTicketIds, bulkTagIds);
      setMessage(`${result.updated_count}件のチケットにタグを追加しました。`);
      setBulkTagIds([]); setBulkOpen(false);
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

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
          <TagMultiSelect tags={tags} selected={tagIds} onChange={setTagIds} label="タグ（いずれかを含む）" />
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
      <section className="bulk-ticket-toolbar">
        <label><input type="checkbox" checked={sortedTickets.length > 0 && selectedTicketIds.length === sortedTickets.length} onChange={(e) => setSelectedTicketIds(e.target.checked ? sortedTickets.map((ticket) => ticket.id) : [])} />表示中をすべて選択</label>
        <span>{selectedTicketIds.length}件選択中</span>
        <button className="secondary" disabled={!selectedTicketIds.length} onClick={() => setBulkOpen(!bulkOpen)}><Tags size={17} />タグを一括付与</button>
      </section>
      {bulkOpen && <section className="bulk-tag-panel">
        <TagMultiSelect tags={tags} selected={bulkTagIds} onChange={setBulkTagIds} label="追加するタグ" />
        <p className="hint">既存のタグは残したまま、選択したタグを追加します。</p>
        <button disabled={busy || !bulkTagIds.length || !selectedTicketIds.length} onClick={() => void applyTags()}>{busy ? "付与中…" : `${selectedTicketIds.length}件に付与`}</button>
      </section>}
      {error && <div role="alert" className="error">{error}</div>}
      {message && <div role="status" className="success">{message}</div>}
      <div className="list selectable-ticket-list">{sortedTickets.map((t) => <div key={t.id} className={selectedTicketIds.includes(t.id) ? "selectable-ticket selected" : "selectable-ticket"}>
        <label className="ticket-select"><input type="checkbox" checked={selectedTicketIds.includes(t.id)} onChange={() => toggleTicket(t.id)} /><span className="sr-only">{t.title}を選択</span></label>
        <TicketCard users={users} categories={categories} tags={tags} ticket={t} onClick={() => openDetail(t.id)} />
      </div>)}</div>
    </main>
  );
}
