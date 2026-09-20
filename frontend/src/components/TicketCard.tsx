import { ChevronRight } from "lucide-react";
import type { Category, Tag, Ticket, User } from "../types";
import { formatYen, userPair } from "../utils/display";
import { StatusBadge } from "./StatusBadge";
import { CategoryIcon, categoryForName } from "./CategoryIcon";

export function TicketCard({ ticket, users, categories, tags = [], onClick }: { ticket: Ticket; users: User[]; categories: Category[]; tags?: Tag[]; onClick: () => void }) {
  const pair = userPair(users);

  return (
    <button className="ticket-card" onClick={onClick}>
      <div className="ticket-main">
        <div className="ticket-row">
          <strong>{ticket.title}</strong>
          <StatusBadge status={ticket.status} />
        </div>
        <div className="ticket-id">チケットID: {ticket.display_id || "-"}</div>
        <div className="ticket-tags">{tags.filter((tag) => ticket.tag_ids?.includes(tag.id)).map((tag) => <span key={tag.id}>#{tag.name}</span>)}</div>
        <div className="muted">{ticket.date} / 支払: {ticket.payer_name}</div>
        <div className="category-pill"><CategoryIcon category={categoryForName(categories, ticket.category || "その他")} size={14} />{ticket.category || "その他"}</div>
        <div className="split">
          <span>{pair.first} {formatYen(ticket.share_f)}</span>
          <span>{pair.second} {formatYen(ticket.share_o)}</span>
        </div>
      </div>
      <div className="amount">{formatYen(ticket.amount)}</div>
      <ChevronRight size={18} />
    </button>
  );
}
