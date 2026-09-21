import type { Tag } from "../types";

export function TagMultiSelect({
  tags,
  selected,
  onChange,
  label = "タグ",
  emptyText = "タグがまだありません。設定から作成できます。"
}: {
  tags: Tag[];
  selected: string[];
  onChange: (tagIds: string[]) => void;
  label?: string;
  emptyText?: string;
}) {
  function toggle(tagId: string) {
    onChange(selected.includes(tagId) ? selected.filter((id) => id !== tagId) : [...selected, tagId]);
  }

  return (
    <fieldset className="tag-multi-select">
      <legend>{label}{selected.length ? `（${selected.length}件選択）` : ""}</legend>
      {tags.length > 0 ? <div className="tag-multi-options">
        {tags.map((tag) => <label key={tag.id} className={selected.includes(tag.id) ? "selected" : ""}>
          <input type="checkbox" checked={selected.includes(tag.id)} onChange={() => toggle(tag.id)} />
          <span>#{tag.name}</span>
        </label>)}
      </div> : <small>{emptyText}</small>}
      {selected.length > 0 && <button type="button" className="tag-clear-button" onClick={() => onChange([])}>選択を解除</button>}
    </fieldset>
  );
}
