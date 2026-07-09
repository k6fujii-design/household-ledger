import type { View } from "../App";
import { api } from "../api/client";
import { TicketForm } from "../components/TicketForm";
import type { Category, TicketInput, TicketTemplate, User } from "../types";

export function TicketCreatePage({
  users,
  categories,
  templates,
  draft,
  setView,
  onDone
}: {
  users: User[];
  categories: Category[];
  templates: TicketTemplate[];
  draft: TicketInput | null;
  setView: (view: View) => void;
  onDone: () => void;
}) {
  async function submit(payload: TicketInput) {
    await api.createTicket(payload);
    onDone();
    setView("home");
  }
  return (
    <main className="screen record-screen">
      <header className="record-head">
        <h1>{draft ? "コピーして新規作成" : "新規チケット"}</h1>
      </header>
      <TicketForm users={users} categories={categories} templates={templates} draft={draft} onSubmit={submit} onCancel={() => { onDone(); setView("home"); }} />
    </main>
  );
}
