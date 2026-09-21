import { useEffect, useState } from "react";
import { Pencil, Plus, Save, Trash2 } from "lucide-react";
import { api } from "../api/client";
import type { AgentMemory, Tag } from "../types";

export function PreferencesPanel({ kind, scope = "personal", displayName = "" }: { kind: "tags" | "memories"; scope?: "personal" | "shared"; displayName?: string }) {
  const [rows, setRows] = useState<(Tag | AgentMemory)[]>([]);
  const [value, setValue] = useState("");
  const [editing, setEditing] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function reload() { setRows(kind === "tags" ? await api.tags() : await api.memories(scope)); }
  useEffect(() => { reload().catch((e) => setError(e.message)); }, [kind]);
  async function run(action: () => Promise<unknown>) {
    setBusy(true); setError("");
    try { await action(); await reload(); } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <section className="settings-panel preference-panel">
    <form onSubmit={(e) => { e.preventDefault(); void run(async () => {
      if (kind === "tags") await api.saveTag(value, editing); else await api.saveMemory(value, scope);
      setValue(""); setEditing(undefined);
    }); }}>
      {kind === "tags" ? <label>タグ名
        <span className="tag-name-input"><b aria-hidden="true">#</b><input required maxLength={60} value={value} onChange={(e) => setValue(e.target.value.replace(/^[#＃]+/, ""))} placeholder="北海道旅行" /></span>
        <small>保存すると先頭に # が付きます。例: #北海道旅行</small>
      </label> : <label>{scope === "shared" ? "共通の注意事項" : `${displayName}向けの注意事項`}
        <textarea required maxLength={500} value={value} onChange={(e) => setValue(e.target.value)} />
      </label>}
      <button disabled={busy || !value.trim()}>{editing ? <Save size={18} /> : <Plus size={18} />}{editing ? "保存" : "追加"}</button>
      {editing && <button type="button" className="secondary" onClick={() => { setEditing(undefined); setValue(""); }}>キャンセル</button>}
    </form>
    {error && <div role="alert" className="error">{error}</div>}
    <div className="preference-list">{rows.map((row) => <div key={row.id}>
      <span>{"name" in row ? `#${row.name}` : row.content}</span>
      {"name" in row && <button className="icon-button secondary" title="タグ名を編集（チケットとの関連は維持されます）" aria-label={`${row.name}のタグ名を編集`} onClick={() => { setEditing(row.id); setValue(row.name); }}><Pencil size={16} /></button>}
      <button className="icon-button danger" disabled={busy} title="削除" aria-label="削除" onClick={() => {
        if (confirm(kind === "memories" && scope === "shared" ? "共通の注意事項を削除しますか？" : "削除しますか？")) void run(() => kind === "tags" ? api.deleteTag(row.id) : api.deleteMemory(row.id, scope));
      }}><Trash2 size={16} /></button>
    </div>)}</div>
    {!rows.length && <div className="empty-state">まだ登録されていません。</div>}
  </section>;
}
