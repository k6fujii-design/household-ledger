import { LogOut, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { AppSettings, Category, TicketTemplate, TicketTemplateInput, User } from "../types";

const emptyTemplate: TicketTemplateInput = {
  name: "",
  title: "",
  amount: 1000,
  payer_user_id: null,
  ratio_f: 5,
  ratio_o: 5,
  status: "new",
  category: "",
  memo: ""
};

export function SettingsPage({
  user,
  users,
  categories,
  templates,
  settings,
  onSharedChange,
  onLogout
}: {
  user: User;
  users: User[];
  categories: Category[];
  templates: TicketTemplate[];
  settings: AppSettings;
  onSharedChange: () => Promise<User[]>;
  onLogout: () => void;
}) {
  const [names, setNames] = useState<Record<string, string>>({});
  const [closingDay, setClosingDay] = useState(settings.closing_day);
  const [categoryName, setCategoryName] = useState("");
  const [categoryColor, setCategoryColor] = useState("#ff8f70");
  const [template, setTemplate] = useState<TicketTemplateInput>(emptyTemplate);
  const [message, setMessage] = useState("");

  const categoryOptions = useMemo(() => categories.map((row) => row.name), [categories]);

  useEffect(() => {
    setNames(Object.fromEntries(users.map((u) => [u.id, u.name])));
    setClosingDay(settings.closing_day);
  }, [users, settings]);

  async function saveNames() {
    setMessage("");
    for (const row of users) {
      const name = names[row.id]?.trim();
      if (name && name !== row.name) {
        await api.updateUser(row.id, name);
      }
    }
    await onSharedChange();
    setMessage("表示名を保存しました。");
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

  return (
    <main className="screen">
      <header className="top"><h1>設定</h1></header>
      <section className="settings">
        <div><span>ログイン中</span><strong>{user.name}</strong><small>{user.email}</small></div>

        <div className="settings-panel">
          <span>表示名</span>
          {users.map((row) => (
            <label key={row.id}>{row.email}<input value={names[row.id] || ""} onChange={(e) => setNames({ ...names, [row.id]: e.target.value })} /></label>
          ))}
          <button onClick={saveNames}><Save size={18} />表示名を保存</button>
        </div>

        <div className="settings-panel">
          <span>締め日</span>
          <label>毎月<input type="number" min={1} max={31} value={closingDay} onChange={(e) => setClosingDay(Number(e.target.value))} />日締め</label>
          <button onClick={saveClosingDay}><Save size={18} />締め日を保存</button>
        </div>

        <div className="settings-panel">
          <span>カテゴリ</span>
          <div className="inline-fields">
            <input value={categoryName} onChange={(e) => setCategoryName(e.target.value)} placeholder="食費、家賃など" />
            <input type="color" value={categoryColor} onChange={(e) => setCategoryColor(e.target.value)} aria-label="カテゴリ色" />
            <button onClick={addCategory}><Plus size={18} />追加</button>
          </div>
          <div className="editable-list">
            {categories.map((row) => (
              <div key={row.id}>
                <span><i className="color-dot" style={{ background: row.color }} />{row.name}</span>
                <button className="danger icon-button" onClick={() => removeCategory(row.id)}><Trash2 size={16} /></button>
              </div>
            ))}
          </div>
        </div>

        <div className="settings-panel">
          <span>チケットテンプレート</span>
          <label>テンプレート名<input value={template.name} onChange={(e) => setTemplate({ ...template, name: e.target.value })} placeholder="家賃、サブスクなど" /></label>
          <label>概要<input value={template.title} onChange={(e) => setTemplate({ ...template, title: e.target.value })} /></label>
          <label>金額<input type="number" min={1} value={template.amount} onChange={(e) => setTemplate({ ...template, amount: Number(e.target.value) })} /></label>
          <label>支払者<select value={template.payer_user_id || ""} onChange={(e) => setTemplate({ ...template, payer_user_id: e.target.value || null })}><option value="">作成時に選ぶ</option>{users.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
          <label>カテゴリ<select value={template.category} onChange={(e) => setTemplate({ ...template, category: e.target.value })}><option value="">未設定</option>{categoryOptions.map((name) => <option key={name} value={name}>{name}</option>)}</select></label>
          <div className="ratio-inputs">
            <label>比率1<input type="number" min={0} value={template.ratio_f} onChange={(e) => setTemplate({ ...template, ratio_f: Number(e.target.value) })} /></label>
            <label>比率2<input type="number" min={0} value={template.ratio_o} onChange={(e) => setTemplate({ ...template, ratio_o: Number(e.target.value) })} /></label>
          </div>
          <label>メモ<textarea value={template.memo} onChange={(e) => setTemplate({ ...template, memo: e.target.value })} /></label>
          <button onClick={addTemplate}><Plus size={18} />テンプレート追加</button>
          <div className="editable-list">
            {templates.map((row) => (
              <div key={row.id}>
                <span>{row.name}<small>{row.title}</small></span>
                <button className="danger icon-button" onClick={() => removeTemplate(row.id)}><Trash2 size={16} /></button>
              </div>
            ))}
          </div>
        </div>

        {message && <div className="success">{message}</div>}
        <button className="danger" onClick={logout}><LogOut size={18} />ログアウト</button>
      </section>
    </main>
  );
}
