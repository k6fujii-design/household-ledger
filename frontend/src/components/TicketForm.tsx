import { ArrowLeft, CopyCheck, Save, Trash2 } from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import type { Category, Ticket, TicketInput, TicketTemplate, User } from "../types";
import { formatYen, userPair } from "../utils/display";

const presets = [
  [5, 5],
  [6, 4],
  [7, 3],
  [8, 2],
  [10, 0],
  [0, 10]
];

const amountShortcuts = [100, 500, 1000];
const today = new Date().toISOString().slice(0, 10);

function normalizeRatio(value: string) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(10, parsed));
}

export function TicketForm({
  users,
  categories,
  templates,
  ticket,
  draft,
  onSubmit,
  onDelete,
  onCancel,
  onClone
}: {
  users: User[];
  categories: Category[];
  templates: TicketTemplate[];
  ticket?: Ticket;
  draft?: TicketInput | null;
  onSubmit: (payload: TicketInput) => Promise<void>;
  onDelete?: () => Promise<void>;
  onCancel?: () => void;
  onClone?: () => void;
}) {
  const pair = userPair(users);
  const initialPayer = ticket?.payer_user_id || draft?.payer_user_id || users[0]?.id || "";
  const [form, setForm] = useState<TicketInput>({
    date: ticket?.date || draft?.date || today,
    title: ticket?.title || draft?.title || "",
    amount: ticket?.amount || draft?.amount || 1000,
    payer_user_id: initialPayer,
    ratio_f: ticket?.ratio_f ?? draft?.ratio_f ?? 5,
    ratio_o: ticket?.ratio_o ?? draft?.ratio_o ?? 5,
    status: ticket?.status || draft?.status || "new",
    category: ticket?.category || draft?.category || "",
    memo: ticket?.memo || draft?.memo || ""
  });
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ticket && draft) setForm(draft);
  }, [draft, ticket]);

  const shares = useMemo(() => {
    const total = form.ratio_f + form.ratio_o;
    const f = total ? Math.round(form.amount * form.ratio_f / total) : 0;
    return { f, o: form.amount - f };
  }, [form]);

  function setFirstRatio(value: string) {
    const ratio = normalizeRatio(value);
    setForm({ ...form, ratio_f: ratio, ratio_o: 10 - ratio });
  }

  function setSecondRatio(value: string) {
    const ratio = normalizeRatio(value);
    setForm({ ...form, ratio_f: 10 - ratio, ratio_o: ratio });
  }

  function applyTemplate(templateId: string) {
    const template = templates.find((row) => row.id === templateId);
    if (!template) return;
    setForm({
      ...form,
      title: template.title,
      amount: template.amount,
      payer_user_id: template.payer_user_id || form.payer_user_id,
      ratio_f: template.ratio_f,
      ratio_o: template.ratio_o,
      status: template.status,
      category: template.category,
      memo: template.memo
    });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!form.title.trim()) return setError("概要を入力してください");
    if (form.amount < 1) return setError("金額は1円以上で入力してください");
    if (form.ratio_f + form.ratio_o === 0) return setError("負担比率を入力してください");
    try {
      await onSubmit(form);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存に失敗しました");
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      {error && <div className="error">{error}</div>}
      {templates.length > 0 && (
        <label>テンプレート
          <select defaultValue="" onChange={(e) => applyTemplate(e.target.value)}>
            <option value="">選択してください</option>
            {templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
          </select>
        </label>
      )}
      <label>日付<input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></label>
      <label>概要<input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="食費、日用品、交通費など" /></label>
      <label>金額<input type="number" min={1} value={form.amount} onChange={(e) => setForm({ ...form, amount: Number(e.target.value) })} /></label>
      <div className="preset-row amount-shortcuts">
        {amountShortcuts.map((amount) => <button type="button" className="chip" key={amount} onClick={() => setForm({ ...form, amount: form.amount + amount })}>+{amount}</button>)}
      </div>
      <label>カテゴリ
        <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
          <option value="">未設定</option>
          {categories.map((category) => <option key={category.id} value={category.name}>{category.name}</option>)}
        </select>
      </label>
      {categories.length > 0 && (
        <div className="preset-row">
          {categories.map((category) => (
            <button type="button" key={category.id} className={form.category === category.name ? "chip on" : "chip"} onClick={() => setForm({ ...form, category: category.name })}>
              <span className="color-dot" style={{ background: category.color }} />{category.name}
            </button>
          ))}
        </div>
      )}
      <label>支払者<select value={form.payer_user_id} onChange={(e) => setForm({ ...form, payer_user_id: e.target.value })}>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
      <div>
        <span className="label">負担比率</span>
        <div className="preset-row">
          {presets.map(([f, o]) => (
            <button type="button" key={`${f}:${o}`} className={form.ratio_f === f && form.ratio_o === o ? "chip on" : "chip"} onClick={() => setForm({ ...form, ratio_f: f, ratio_o: o })}>
              {f}:{o}
            </button>
          ))}
        </div>
      </div>
      <div className="ratio-inputs">
        <label>{pair.first}<input type="number" min={0} max={10} value={form.ratio_f} onChange={(e) => setFirstRatio(e.target.value)} /></label>
        <label>{pair.second}<input type="number" min={0} max={10} value={form.ratio_o} onChange={(e) => setSecondRatio(e.target.value)} /></label>
      </div>
      <div className="calc">負担額: {pair.first} {formatYen(shares.f)} / {pair.second} {formatYen(shares.o)}</div>
      <label>ステータス<select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as TicketInput["status"] })}><option value="new">未精算</option><option value="settled">精算済み</option><option value="canceled">取り消し</option></select></label>
      <label>メモ<textarea value={form.memo} onChange={(e) => setForm({ ...form, memo: e.target.value })} /></label>
      <div className="actions">
        {onCancel && <button type="button" className="secondary" onClick={onCancel}><ArrowLeft size={18} />戻る</button>}
        {onClone && <button type="button" className="secondary" onClick={onClone}><CopyCheck size={18} />コピー</button>}
        {onDelete && <button type="button" className="danger" onClick={onDelete}><Trash2 size={18} />削除</button>}
        <button type="submit"><Save size={18} />保存</button>
      </div>
    </form>
  );
}
