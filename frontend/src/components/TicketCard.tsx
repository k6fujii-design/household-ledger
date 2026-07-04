import { ChevronRight } from "lucide-react";
import type { Ticket, User } from "../types";
import { formatYen, userPair } from "../utils/display";
import { StatusBadge } from "./StatusBadge";

export function TicketCard({ ticket, users, onClick }: { ticket: Ticket; users: User[]; onClick: () => void }) {
  const pair = userPair(users);

  return (
    <button className="ticket-card" onClick={onClick}>
      <div className="ticket-main">
        <div className="ticket-row">
          <strong>{ticket.title}</strong>
          <StatusBadge status={ticket.status} />
        </div>
        <div className="muted">{ticket.date} / 支払: {ticket.payer_name}</div>
        {ticket.category && <div className="category-pill">{ticket.category}</div>}
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
