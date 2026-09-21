import { ArrowLeft, ChevronRight, ExternalLink, Github, History, LogOut, Palette, Plus, ReceiptText, Save, Trash2, UserRound, CalendarClock } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { AppSettings, AuditLog, Category, TicketTemplate, TicketTemplateInput, User } from "../types";
import { CategoryIcon } from "../components/CategoryIcon";
import { PreferencesPanel } from "../components/PreferencesPanel";
import { Brain, Tags } from "lucide-react";

type SettingsSection = "menu" | "names" | "closing" | "categories" | "templates" | "history" | "about" | "tags" | "memories";

const emptyTemplate: TicketTemplateInput = {
  name: "",
  title: "",
  amount: 1000,
  payer_user_id: null,
  ratio_f: 5,
  ratio_o: 5,
  status: "new",
  category: "その他",
  memo: ""
};

const technicalDetailsUrl = "https://github.com/k6fujii-design/household-ledger/tree/main";
const hiddenActions = new Set(["login_success", "login_failure", "logout"]);
const actionLabels: Record<string, string> = {
  ticket_create: "チケット作成",
  ticket_update: "チケット編集",
  ticket_delete: "チケット削除",
  ticket_status_change: "ステータス変更",
  ticket_bulk_status_update: "一括精算",
  setting_update_user_name: "表示名変更",
  setting_update_user_profile: "ユーザー設定変更",
  setting_update_closing_day: "締め日変更",
  setting_create_category: "カテゴリ追加",
  setting_update_category: "カテゴリ編集",
  setting_delete_category: "カテゴリ削除",
  setting_create_template: "テンプレート追加",
  setting_update_template: "テンプレート編集",
  setting_delete_template: "テンプレート削除",
  setting_create_tag: "タグ追加",
  setting_update_tag: "タグ編集",
  setting_delete_tag: "タグ削除",
  ticket_bulk_tag_add: "タグ一括付与",
  agent_memory_create: "AIの記憶追加",
  agent_memory_delete: "AIの記憶削除",
  setting_update_monthly_settlement: "月次メモ更新"
};

function describe(log: AuditLog) {
  const after = log.after || {};
  const before = log.before || {};
  if (typeof after.title === "string") return after.title;
  if (typeof after.name === "string") return after.name;
  if (typeof before.title === "string") return before.title;
  if (typeof before.name === "string") return before.name;
  if (typeof after.period_key === "string") return after.period_key;
  if (typeof after.updated_count === "number") return `${after.updated_count}件`;
  return log.target_type;
}

export function SettingsPage({
  user,
  users,
  categories,
  templates,
  settings,
  onSharedChange,
  openEdit,
  onLogout
}: {
  user: User;
  users: User[];
  categories: Category[];
  templates: TicketTemplate[];
  settings: AppSettings;
  onSharedChange: () => Promise<User[]>;
  openEdit: (id: string) => void;
  onLogout: () => void;
}) {
  const [section, setSection] = useState<SettingsSection>("menu");
  const [memoryScope, setMemoryScope] = useState<"shared" | "personal">("personal");
  const [names, setNames] = useState<Record<string, string>>({});
  const [lineUserIds, setLineUserIds] = useState<Record<string, string>>({});
  const [closingDay, setClosingDay] = useState(settings.closing_day);
  const [categoryName, setCategoryName] = useState("");
  const [categoryColor, setCategoryColor] = useState("#ff8f70");
  const [template, setTemplate] = useState<TicketTemplateInput>(emptyTemplate);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [message, setMessage] = useState("");
  const categoryOptions = useMemo(() => categories.map((row) => row.name), [categories]);

  useEffect(() => {
    setNames(Object.fromEntries(users.map((u) => [u.id, u.name])));
    setLineUserIds(Object.fromEntries(users.map((u) => [u.id, u.line_user_id || ""])));
    setClosingDay(settings.closing_day);
  }, [users, settings]);

  useEffect(() => {
    if (section === "history") api.auditLogs(150).then(setLogs);
  }, [section]);

  async function saveNames() {
    setMessage("");
    for (const row of users) {
      const name = names[row.id]?.trim();
      const lineUserId = lineUserIds[row.id]?.trim() || null;
      if (name && (name !== row.name || lineUserId !== (row.line_user_id || null))) await api.updateUser(row.id, name, lineUserId);
    }
    await onSharedChange();
    setMessage("ユーザー設定を保存しました。");
  }

  async function saveClosingDay() {
    await api.updateSettings({ closing_day: closingDay });
    await onSharedChange();
    setMessage("締め日を保存しました。");
  }

  async function addCategory() {
    if (!categoryName.trim()) return;
    await api.createCategory({ name: categoryName.trim(), color: categoryColor });
    setCategoryName("");
    await onSharedChange();
  }

  async function removeCategory(id: string) {
    if (!confirm("カテゴリを削除しますか？既存チケットのカテゴリ名はそのまま残ります。")) return;
    await api.deleteCategory(id);
    await onSharedChange();
  }

  async function addTemplate() {
    if (!template.name.trim() || !template.title.trim()) return;
    await api.createTemplate(template);
    setTemplate(emptyTemplate);
    await onSharedChange();
  }

  async function removeTemplate(id: string) {
    if (!confirm("テンプレートを削除しますか？")) return;
    await api.deleteTemplate(id);
    await onSharedChange();
  }

  async function logout() {
    await api.logout();
    onLogout();
  }

  const backButton = section !== "menu" && (
    <button className="secondary" onClick={() => { setSection("menu"); setMessage(""); }}><ArrowLeft size={18} />設定へ戻る</button>
  );

  return (
    <main className="screen settings-screen">
      <header className="settings-title">
        <h1>{section === "menu" ? "設定" : {
          names: "ユーザー設定",
          closing: "締め日",
          categories: "カテゴリ",
          templates: "チケットテンプレート",
          tags: "タグ",
          memories: "AIの記憶",
          history: "履歴",
          about: "アプリ情報"
        }[section]}</h1>
        {backButton}
      </header>

      {section === "menu" && (
        <section className="settings-menu">
          <article className="login-card"><span>ログイン中</span><strong>{user.name}</strong><small>{user.email}</small></article>
          {[
            { key: "names", label: "ユーザー設定", Icon: UserRound },
            { key: "closing", label: "締め日", Icon: CalendarClock },
            { key: "categories", label: "カテゴリ", Icon: Palette },
            { key: "templates", label: "チケットテンプレート", Icon: ReceiptText },
            { key: "tags", label: "タグ", Icon: Tags },
            { key: "memories", label: "AIの記憶", Icon: Brain },
            { key: "history", label: "履歴", Icon: History },
            { key: "about", label: "技術詳細", Icon: Github }
          ].map(({ key, label, Icon }) => (
            <button key={key} className="settings-menu-item" onClick={() => setSection(key as SettingsSection)}>
              <Icon size={22} />
              <span>{label}</span>
              <ChevronRight size={22} />
            </button>
          ))}
          <button className="danger" onClick={logout}><LogOut size={18} />ログアウト</button>
        </section>
      )}

      {section === "memories" && <div className="segmented memory-scopes">
        <button aria-pressed={memoryScope === "shared"} className={memoryScope === "shared" ? "on" : ""} onClick={() => setMemoryScope("shared")}>共通</button>
        <button aria-pressed={memoryScope === "personal"} className={memoryScope === "personal" ? "on" : ""} onClick={() => setMemoryScope("personal")}>{users.find((row) => row.id === user.id)?.name || user.name}向け</button>
      </div>}
      {(section === "tags" || section === "memories") && <PreferencesPanel key={`${section}-${memoryScope}`} kind={section} scope={memoryScope} displayName={users.find((row) => row.id === user.id)?.name || user.name} />}
      {section === "names" && <section className="settings-panel page-panel">
        {users.map((row) => (
          <div key={row.id} className="user-profile-fields">
            <strong>{row.email}</strong>
            <label>表示名<input value={names[row.id] || ""} onChange={(e) => setNames({ ...names, [row.id]: e.target.value })} /></label>
            <label>LINEユーザーID<input value={lineUserIds[row.id] || ""} onChange={(e) => setLineUserIds({ ...lineUserIds, [row.id]: e.target.value })} placeholder="Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" /></label>
          </div>
        ))}
        <button onClick={saveNames}><Save size={18} />ユーザー設定を保存</button>
      </section>}

      {section === "closing" && <section className="settings-panel page-panel">
        <label>毎月<input type="number" min={1} max={31} value={closingDay} onChange={(e) => setClosingDay(Number(e.target.value))} />日締め</label>
        <button onClick={saveClosingDay}><Save size={18} />締め日を保存</button>
      </section>}

      {section === "categories" && <section className="settings-panel page-panel">
        <div className="inline-fields">
          <input value={categoryName} onChange={(e) => setCategoryName(e.target.value)} placeholder="食費、家賃など" />
          <input type="color" value={categoryColor} onChange={(e) => setCategoryColor(e.target.value)} aria-label="カテゴリ色" />
          <button onClick={addCategory}><Plus size={18} />追加</button>
        </div>
        <div className="editable-list category-settings-list">{categories.map((row) => (
          <div key={row.id}><CategoryIcon category={row} size={20} /><span><strong>{row.name}</strong>{row.description && <small>{row.description}</small>}</span><button className="danger icon-button" onClick={() => removeCategory(row.id)}><Trash2 size={16} /></button></div>
        ))}</div>
      </section>}

      {section === "templates" && <section className="settings-panel page-panel">
        <label>テンプレート名<input value={template.name} onChange={(e) => setTemplate({ ...template, name: e.target.value })} placeholder="家賃、サブスクなど" /></label>
        <label>概要<input value={template.title} onChange={(e) => setTemplate({ ...template, title: e.target.value })} /></label>
        <label>金額<input type="number" min={1} value={template.amount} onChange={(e) => setTemplate({ ...template, amount: Number(e.target.value) })} /></label>
        <label>支払者<select value={template.payer_user_id || ""} onChange={(e) => setTemplate({ ...template, payer_user_id: e.target.value || null })}><option value="">作成時に選ぶ</option>{users.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        <label>カテゴリ<select value={template.category} onChange={(e) => setTemplate({ ...template, category: e.target.value })}>{categoryOptions.map((name) => <option key={name} value={name}>{name}</option>)}</select></label>
        <div className="ratio-inputs"><label>比率1<input type="number" min={0} value={template.ratio_f} onChange={(e) => setTemplate({ ...template, ratio_f: Number(e.target.value), ratio_o: 10 - Number(e.target.value) })} /></label><label>比率2<input type="number" min={0} value={template.ratio_o} onChange={(e) => setTemplate({ ...template, ratio_f: 10 - Number(e.target.value), ratio_o: Number(e.target.value) })} /></label></div>
        <label>メモ<textarea value={template.memo} onChange={(e) => setTemplate({ ...template, memo: e.target.value })} /></label>
        <button onClick={addTemplate}><Plus size={18} />テンプレート追加</button>
        <div className="editable-list">{templates.map((row) => <div key={row.id}><span>{row.name}<small>{row.title}</small></span><button className="danger icon-button" onClick={() => removeTemplate(row.id)}><Trash2 size={16} /></button></div>)}</div>
      </section>}

      {section === "history" && <section className="history-list">
        {logs.filter((log) => !hiddenActions.has(log.action)).map((log) => {
          const canOpen = Boolean(log.target_id && log.target_type === "ticket" && log.action !== "ticket_bulk_status_update" && log.action !== "ticket_delete");
          const content = <><div><strong>{actionLabels[log.action] || log.action}</strong><span>{describe(log)}</span></div><div className="history-meta"><span>{log.actor_name || "system"}</span><time>{new Date(log.created_at).toLocaleString("ja-JP")}</time></div></>;
          return canOpen ? <button key={log.id} className="history-item history-link" onClick={() => openEdit(log.target_id!)}><span className="history-link-body">{content}</span><ExternalLink size={16} /></button> : <article key={log.id} className="history-item">{content}</article>;
        })}
      </section>}

      {section === "about" && <section className="settings-panel page-panel tech-details">
        <span>アプリ情報</span>
        <small>構成、デプロイ手順、ソースコードはGitHubで確認できます。</small>
        <a href={technicalDetailsUrl} target="_blank" rel="noreferrer" className="external-link-button"><Github size={18} />技術詳細を見る<ExternalLink size={16} /></a>
      </section>}

      {message && <div className="success">{message}</div>}
    </main>
  );
}
