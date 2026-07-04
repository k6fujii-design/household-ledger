import { useEffect, useState } from "react";
import type { View } from "../App";
import { api } from "../api/client";
import { TicketForm } from "../components/TicketForm";
import type { Category, Ticket, TicketInput, TicketTemplate, User } from "../types";

export function TicketEditPage({
  id,
  users,
  categories,
  templates,
  setView,
  onClone
}: {
  id: string;
  users: User[];
  categories: Category[];
  templates: TicketTemplate[];
  setView: (view: View) => void;
  onClone: (id: string) => void;
}) {
  const [ticket, setTicket] = useState<Ticket | null>(null);
  useEffect(() => { api.ticket(id).then(setTicket); }, [id]);
  async function submit(payload: TicketInput) {
    await api.updateTicket(id, payload);
    setView("tickets");
  }
  async function remove() {
    if (confirm("このチケットを削除しますか？")) {
      await api.deleteTicket(id);
      setView("tickets");
    }
  }
  return <main className="screen"><header className="top"><h1>チケット編集</h1></header>{ticket ? <TicketForm users={users} categories={categories} templates={templates} ticket={ticket} onSubmit={submit} onDelete={remove} onCancel={() => setView("tickets")} onClone={() => onClone(id)} /> : "読み込み中..."}</main>;
}
