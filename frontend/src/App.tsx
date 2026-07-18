import { useEffect, useState } from "react";
import { BottomNav } from "./components/BottomNav";
import { api } from "./api/client";
import type { AppSettings, Category, TicketInput, TicketTemplate, User } from "./types";
import { LoginPage } from "./pages/LoginPage";
import { HomePage } from "./pages/HomePage";
import { TicketListPage } from "./pages/TicketListPage";
import { TicketCreatePage } from "./pages/TicketCreatePage";
import { TicketEditPage } from "./pages/TicketEditPage";
import { TicketDetailPage } from "./pages/TicketDetailPage";
import { SummaryPage } from "./pages/SummaryPage";
import { CalendarPage } from "./pages/CalendarPage";
import { HistoryPage } from "./pages/HistoryPage";
import { SettingsPage } from "./pages/SettingsPage";

export type View = "home" | "tickets" | "create" | "detail" | "edit" | "summary" | "calendar" | "history" | "settings";

type AppHistoryState = {
  view: View;
  editId?: string | null;
};

const defaultSettings: AppSettings = { closing_day: 31 };
const views: View[] = ["home", "tickets", "create", "detail", "edit", "summary", "calendar", "history", "settings"];

function viewFromHash(): View {
  const hash = window.location.hash.replace("#", "");
  const viewName = hash.startsWith("edit-") ? "edit" : hash.startsWith("detail-") ? "detail" : hash;
  return views.includes(viewName as View) ? viewName as View : "home";
}

function editIdFromHash() {
  const hash = window.location.hash.replace("#", "");
  return hash.startsWith("edit-") ? hash.slice(5) : hash.startsWith("detail-") ? hash.slice(7) : null;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [categories, setCategories] = useState<Category[]>([]);
  const [templates, setTemplates] = useState<TicketTemplate[]>([]);
  const [view, setViewState] = useState<View>(() => viewFromHash());
  const [editId, setEditId] = useState<string | null>(() => editIdFromHash());
  const [cloneDraft, setCloneDraft] = useState<TicketInput | null>(null);
  const [loading, setLoading] = useState(true);

  function navigate(nextView: View, options: { replace?: boolean; editId?: string | null } = {}) {
    const hasTicket = nextView === "edit" || nextView === "detail";
    const nextEditId = hasTicket ? options.editId || editId : null;
    const url = hasTicket && nextEditId ? `#${nextView}-${nextEditId}` : `#${nextView}`;
    const state: AppHistoryState = { view: nextView, editId: nextEditId };
    if (options.replace) {
      window.history.replaceState(state, "", url);
    } else {
      window.history.pushState(state, "", url);
    }
    setViewState(nextView);
    setEditId(nextEditId);
    if (nextView !== "create") setCloneDraft(null);
  }

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
    if (!window.history.state?.view) {
      window.history.replaceState({ view, editId }, "", (view === "edit" || view === "detail") && editId ? `#${view}-${editId}` : `#${view}`);
    }
    const handlePopState = (event: PopStateEvent) => {
      const state = event.state as AppHistoryState | null;
      const nextView = state?.view || viewFromHash();
      const nextEditId = nextView === "edit" || nextView === "detail" ? state?.editId || editIdFromHash() : null;
      setViewState(nextView);
      setEditId(nextEditId);
      if (nextView !== "create") setCloneDraft(null);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    loadSession();
  }, []);

  if (loading) return <div className="screen center">読み込み中...</div>;
  if (!user) return <LoginPage onLogin={loadSession} />;

  const openEdit = (id: string) => {
    navigate("edit", { editId: id });
  };

  const openDetail = (id: string) => {
    navigate("detail", { editId: id });
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
    navigate("create");
  };

  const createTicketOnDate = (date: string) => {
    setCloneDraft({
      date,
      title: "",
      amount: 0,
      payer_user_id: users[0]?.id || "",
      ratio_f: 5,
      ratio_o: 5,
      status: "new",
      category: "その他",
      memo: ""
    });
    navigate("create");
  };

  return (
    <div className="app-shell">
      {view === "home" && <HomePage users={users} categories={categories} settings={settings} setView={navigate} openDetail={openDetail} />}
      {view === "tickets" && <TicketListPage users={users} categories={categories} setView={navigate} openDetail={openDetail} />}
      {view === "create" && <TicketCreatePage users={users} categories={categories} templates={templates} draft={cloneDraft} setView={navigate} onDone={() => setCloneDraft(null)} />}
      {view === "detail" && editId && <TicketDetailPage id={editId} users={users} categories={categories} onBack={() => navigate("tickets")} onEdit={openEdit} />}
      {view === "edit" && editId && <TicketEditPage id={editId} users={users} categories={categories} templates={templates} setView={navigate} onClone={cloneTicket} />}
      {view === "summary" && <SummaryPage users={users} categories={categories} settings={settings} />}
      {view === "calendar" && <CalendarPage users={users} categories={categories} openEdit={openEdit} openCreate={createTicketOnDate} />}
      {view === "history" && <HistoryPage openEdit={openEdit} />}
      {view === "settings" && <SettingsPage user={user} users={users} categories={categories} templates={templates} settings={settings} onSharedChange={loadShared} openEdit={openEdit} onLogout={() => { setUser(null); navigate("home", { replace: true }); }} />}
      <BottomNav view={view} setView={navigate} />
    </div>
  );
}
