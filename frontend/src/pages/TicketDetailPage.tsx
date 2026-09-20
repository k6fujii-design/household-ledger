import { ArrowLeft, CalendarDays, FileText, Pencil, ReceiptText, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { CategoryIcon, categoryForName } from "../components/CategoryIcon";
import { ShareBar } from "../components/ShareBar";
import { StatusBadge } from "../components/StatusBadge";
import type { Category, Tag, Ticket, User } from "../types";
import { formatYen, userPair } from "../utils/display";

export function TicketDetailPage({ id, users, categories, onBack, onEdit }: {
  id: string;
  users: User[];
  categories: Category[];
  onBack: () => void;
  onEdit: (id: string) => void;
}) {
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [tags, setTags] = useState<Tag[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { api.tags().then(setTags).catch((e) => setError(e.message)); }, []);
  const pair = userPair(users);
  useEffect(() => { api.ticket(id).then(setTicket); }, [id]);

  if (!ticket) return <main className="screen center">読み込み中...</main>;
  const category = categoryForName(categories, ticket.category || "その他");
  const payer = ticket.payer_name || users.find((user) => user.id === ticket.payer_user_id)?.name || "不明";

  return (
    <main className="screen ticket-detail-screen">
      <header className="detail-header">
        <button className="secondary icon-button" onClick={onBack} aria-label="戻る"><ArrowLeft /></button>
        <div><span>チケット #{ticket.display_id || "-"}</span><h1>{ticket.title}</h1></div>
        <button onClick={() => onEdit(id)}><Pencil size={18} />編集</button>
      </header>
      <section className={`detail-amount-card ${ticket.status}`}>
        <span>支出額</span><strong>{formatYen(ticket.amount)}</strong><StatusBadge status={ticket.status} />
      </section>
      <section className="detail-grid">
        <article><CalendarDays /><span>日付</span><strong>{ticket.date}</strong></article>
        <article><UserRound /><span>支払者</span><strong>{payer}</strong></article>
        <article className="detail-category"><CategoryIcon category={category} size={22} /><span>カテゴリ</span><strong>{ticket.category || "その他"}</strong>{category?.description && <small>{category.description}</small>}</article>
        <article><ReceiptText /><span>負担比率</span><strong>{pair.first} {ticket.ratio_f}：{ticket.ratio_o} {pair.second}</strong></article>
      </section>
      <section className="detail-share-card">
        {error && <div role="alert">{error}</div>}
        <div className="ticket-tags">{tags.filter((tag) => ticket.tag_ids?.includes(tag.id)).map((tag) => <span key={tag.id}>#{tag.name}</span>)}</div>
        <h2>二人の負担額</h2>
        <ShareBar users={users} ratioF={ticket.ratio_f} ratioO={ticket.ratio_o} amountF={ticket.share_f} amountO={ticket.share_o} percent />
      </section>
      <section className="detail-memo"><FileText size={20} /><div><span>メモ</span><p>{ticket.memo || "メモはありません"}</p></div></section>
    </main>
  );
}
