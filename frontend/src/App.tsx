import { useEffect, useState } from "react";
import { BottomNav } from "./components/BottomNav";
import { api } from "./api/client";
import type { AppSettings, Category, TicketInput, TicketTemplate, User } from "./types";
import { LoginPage } from "./pages/LoginPage";
import { HomePage } from "./pages/HomePage";
import { TicketListPage } from "./pages/TicketListPage";
import { TicketCreatePage } from "./pages/TicketCreatePage";
import { TicketEditPage } from "./pages/TicketEditPage";
import { SummaryPage } from "./pages/SummaryPage";
import { CalendarPage } from "./pages/CalendarPage";
import { HistoryPage } from "./pages/HistoryPage";
import { SettingsPage } from "./pages/SettingsPage";

export type View = "home" | "tickets" | "create" | "edit" | "summary" | "calendar" | "history" | "settings";

const defaultSettings: AppSettings = { closing_day: 31 };

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [categories, setCategories] = useState<Category[]>([]);
  const [templates, setTemplates] = useState<TicketTemplate[]>([]);
  const [view, setView] = useState<View>("home");
  const [editId, setEditId] = useState<string | null>(null);
  const [cloneDraft, setCloneDraft] = useState<TicketInput | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadShared() {
    const [userRows, appSettings, categoryRows, templateRows] = await Promise.all([
      api.users(),
      api.settings(),
      api.categories(),
      api.templates()
    ]);
    setUsers(userRows);
    setSettings(appSettings);
    setCategories(categoryRows);
    setTemplates(templateRows);
    return userRows;
  }

  async function loadSession() {
    try {
      const me = await api.me();
      setUser(me.user);
      await loadShared();
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSession();
  }, []);

  if (loading) return <div className="screen center">読み込み中...</div>;
  if (!user) return <LoginPage onLogin={loadSession} />;

  const openEdit = (id: string) => {
    setEditId(id);
    setView("edit");
  };

  const cloneTicket = async (id: string) => {
    const ticket = await api.ticket(id);
    setCloneDraft({
      date: new Date().toISOString().slice(0, 10),
      title: ticket.title,
      amount: ticket.amount,
      payer_user_id: ticket.payer_user_id,
      ratio_f: ticket.ratio_f,
      ratio_o: ticket.ratio_o,
      status: "new",
      category: ticket.category,
      memo: ticket.memo
    });
    setView("create");
  };

  const createTicketOnDate = (date: string) => {
    setCloneDraft({
      date,
      title: "",
      amount: 1000,
      payer_user_id: users[0]?.id || "",
      ratio_f: 5,
      ratio_o: 5,
      status: "new",
      category: "",
      memo: ""
    });
    setView("create");
  };

  return (
    <div className="app-shell">
      {view === "home" && <HomePage users={users} categories={categories} settings={settings} setView={setView} openEdit={openEdit} />}
      {view === "tickets" && <TicketListPage users={users} categories={categories} setView={setView} openEdit={openEdit} />}
      {view === "create" && <TicketCreatePage users={users} categories={categories} templates={templates} draft={cloneDraft} setView={setView} onDone={() => setCloneDraft(null)} />}
      {view === "edit" && editId && <TicketEditPage id={editId} users={users} categories={categories} templates={templates} setView={setView} onClone={cloneTicket} />}
      {view === "summary" && <SummaryPage users={users} categories={categories} settings={settings} />}
      {view === "calendar" && <CalendarPage users={users} categories={categories} openEdit={openEdit} openCreate={createTicketOnDate} />}
      {view === "history" && <HistoryPage openEdit={openEdit} />}
      {view === "settings" && <SettingsPage user={user} users={users} categories={categories} templates={templates} settings={settings} onSharedChange={loadShared} openEdit={openEdit} onLogout={() => { setUser(null); setView("home"); }} />}
      <BottomNav view={view} setView={setView} />
    </div>
  );
}
