import { ArrowLeft, CopyCheck, Save, Trash2 } from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { ShareBar } from "./ShareBar";
import type { Category, Ticket, TicketInput, TicketTemplate, User } from "../types";
import { formatYen, userPair } from "../utils/display";
import { CategoryIcon } from "./CategoryIcon";
import { api } from "../api/client";
import type { Tag } from "../types";

const amountShortcuts = [100, 1000, 10000];
const today = new Date().toISOString().slice(0, 10);

function RequiredLabel({ children }: { children: string }) {
  return (
    <span className="field-label">
      {children}
      <span className="required-mark" aria-label="必須">*</span>
    </span>
  );
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
  const [tags, setTags] = useState<Tag[]>([]);
  useEffect(() => { api.tags().then(setTags).catch(() => setError("タグの取得に失敗しました")); }, []);
  const initialPayer = ticket?.payer_user_id || draft?.payer_user_id || users[0]?.id || "";
  const [form, setForm] = useState<TicketInput>({
    date: ticket?.date || draft?.date || today,
    tag_ids: ticket?.tag_ids || draft?.tag_ids || [],
    title: ticket?.title || draft?.title || "",
    amount: ticket?.amount ?? draft?.amount ?? 0,
    payer_user_id: initialPayer,
    ratio_f: ticket?.ratio_f ?? draft?.ratio_f ?? 5,
    ratio_o: ticket?.ratio_o ?? draft?.ratio_o ?? 5,
    status: ticket?.status || draft?.status || "new",
    category: ticket?.category || draft?.category || "その他",
    memo: ticket?.memo || draft?.memo || ""
  });
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ticket && draft) setForm(draft);
  }, [draft, ticket]);

  const shares = useMemo(() => {
    const amount = Number(form.amount) || 0;
    const total = form.ratio_f + form.ratio_o;
    const f = total ? Math.round(amount * form.ratio_f / total) : 0;
    return { f, o: amount - f };
  }, [form]);

  function setRatio(value: string) {
    const parsed = Number(value);
    const ratio = Number.isFinite(parsed) ? Math.max(0, Math.min(10, parsed)) : 5;
    setForm({ ...form, ratio_f: ratio, ratio_o: 10 - ratio });
  }

  function adjustAmount(diff: number) {
    setForm({ ...form, amount: Math.max(0, (Number(form.amount) || 0) + diff) });
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
      category: template.category || "その他",
      memo: template.memo
    });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!form.date) return setError("日付を入力してください");
    if (form.amount < 1) return setError("金額は1円以上で入力してください");
    if (!form.payer_user_id) return setError("支払者を選択してください");
    if (!form.status) return setError("ステータスを選択してください");
    if (form.ratio_f + form.ratio_o === 0) return setError("負担比率を入力してください");
    try {
      await onSubmit({ ...form, title: form.title.trim() || "無題" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存に失敗しました");
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      {error && <div className="error">{error}</div>}
      {templates.length > 0 && (
        <label>
          <span className="field-label">テンプレート</span>
          <select defaultValue="" onChange={(e) => applyTemplate(e.target.value)}>
            <option value="">選択してください</option>
            {templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
          </select>
        </label>
      )}
      <label>
        <RequiredLabel>日付</RequiredLabel>
        <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
      </label>
      <label>
        <span className="field-label">概要</span>
        <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="食費、日用品、交通費など" />
      </label>
      <label>
        <RequiredLabel>金額</RequiredLabel>
        <input type="number" min={1} value={form.amount || ""} onChange={(e) => setForm({ ...form, amount: Number(e.target.value || 0) })} placeholder="0" />
      </label>
      <div className="amount-stepper">
        {amountShortcuts.map((amount) => (
          <button key={`plus-${amount}`} type="button" className="chip amount-plus" onClick={() => adjustAmount(amount)}>+{amount.toLocaleString()}</button>
        ))}
        {amountShortcuts.map((amount) => (
          <button key={`minus-${amount}`} type="button" className="chip amount-minus" onClick={() => adjustAmount(-amount)}>-{amount.toLocaleString()}</button>
        ))}
      </div>
      <label>
        <span className="field-label">カテゴリ</span>
        <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
          {categories.map((category) => <option key={category.id} value={category.name}>{category.name}</option>)}
        </select>
      </label>
      {categories.length > 0 && (
        <div className="preset-row category-preset-grid">
          {categories.map((category) => (
            <button type="button" key={category.id} className={form.category === category.name ? "chip on" : "chip"} onClick={() => setForm({ ...form, category: category.name })}>
              <CategoryIcon category={category} size={14} />{category.name}
            </button>
          ))}
        </div>
      )}
      <label>
        <RequiredLabel>支払者</RequiredLabel>
        <select value={form.payer_user_id} onChange={(e) => setForm({ ...form, payer_user_id: e.target.value })}>
          {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
      </label>
      <div className="ratio-slider-field">
        <span className="label">負担比率</span>
        <div className="ratio-slider-box">
          <ShareBar users={users} ratioF={form.ratio_f} ratioO={form.ratio_o} />
          <input
            type="range"
            min={0}
            max={10}
            step={1}
            value={form.ratio_f}
            onChange={(e) => setRatio(e.target.value)}
            aria-label="負担比率"
          />
        </div>
      </div>
      <div className="calc">負担額: {pair.first} {formatYen(shares.f)} / {pair.second} {formatYen(shares.o)}</div>
      <label>
        <RequiredLabel>ステータス</RequiredLabel>
        <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as TicketInput["status"] })}>
          <option value="new">未精算</option>
          <option value="settled">精算済み</option>
          <option value="canceled">取り消し</option>
        </select>
      </label>
      <label>
        <span className="field-label">メモ</span>
        <textarea value={form.memo} onChange={(e) => setForm({ ...form, memo: e.target.value })} />
      </label>
      <fieldset className="tag-selector">
        <legend>タグ</legend>
        <div className="preset-row">{tags.map((tag) => <label key={tag.id} className="tag-choice">
          <input type="checkbox" checked={(form.tag_ids || []).includes(tag.id)} onChange={(e) => setForm({ ...form, tag_ids: e.target.checked ? [...(form.tag_ids || []), tag.id] : (form.tag_ids || []).filter((id) => id !== tag.id) })} />#{tag.name}
        </label>)}</div>
      </fieldset>
      <div className="actions">
        {onCancel && <button type="button" className="secondary" onClick={onCancel}><ArrowLeft size={18} />戻る</button>}
        {onClone && <button type="button" className="secondary" onClick={onClone}><CopyCheck size={18} />コピー</button>}
        {onDelete && <button type="button" className="danger" onClick={onDelete}><Trash2 size={18} />削除</button>}
        <button type="submit"><Save size={18} />保存</button>
      </div>
    </form>
  );
}
