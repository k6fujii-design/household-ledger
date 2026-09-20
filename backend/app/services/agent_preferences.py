"""Persistent user preferences and shared tags, independent of conversation drafts."""
import re
from typing import Any


def memory_scope(text: str) -> str:
    return "shared" if re.search(r"共通|全員|二人|2人|ふたり", text) else "personal"


def preference_command(text: str, ai: dict, user: dict, store: Any) -> str | None:
    intent = ai.get("intent")
    scope = memory_scope(text)
    scope_label = "共通" if scope == "shared" else f"{user['name']}向け"
    # Model classification alone must never turn ordinary conversation into a memory write.
    if intent == "remember" and re.search(r"覚え|記憶|今後|これから", text):
        content = str(ai.get("memory_content") or "").strip()
        if not content:
            return "覚えておく注意事項を具体的に教えてください。"
        row = store.save_memory(str(user["id"]), content, scope)
        store.write_audit("agent_memory_create", "memory", user["id"], row["id"], after={"scope": scope})
        return f"覚えました（{scope_label}）。今後の参考にします。\n{row['content']}\n設定の「AIの記憶」から確認・削除できます。"
    if intent == "list_memories":
        rows = store.list_memories(str(user["id"]), scope)
        return f"覚えている注意事項（{scope_label}）:\n" + ("\n".join(f"・{r['content']}" for r in rows) or "まだありません。")
    if intent == "forget_memory" and re.search(r"忘れ|記憶.*削除|注意事項.*削除", text):
        rows = store.list_memories(str(user["id"]), scope)
        matches = [r for r in rows if r["id"] == ai.get("memory_id")]
        if len(matches) != 1:
            return "どの注意事項を忘れるか、内容を指定してください。設定画面からも削除できます。"
        store.delete_memory(str(user["id"]), matches[0]["id"], scope)
        store.write_audit("agent_memory_delete", "memory", user["id"], matches[0]["id"], before={"scope": scope})
        return f"注意事項を削除しました。\n{matches[0]['content']}"
    if intent == "create_tag":
        name = str(ai.get("tag_name") or "").strip()
        if not name:
            return "作成するタグ名を教えてください。"
        row = store.save_tag(name)
        store.write_audit("setting_create_tag", "tag", user["id"], row["id"], after={"name": row["name"]})
        return f"タグ「#{row['name']}」を用意しました。チケット登録時に指定できます。"
    if intent == "list_tags":
        return "タグ一覧:\n" + ("\n".join(f"#{r['name']}" for r in store.list_tags()) or "まだありません。")
    if intent in {"rename_tag", "delete_tag"}:
        name = str(ai.get("tag_name") or "").strip().lstrip("#＃")
        row = next((r for r in store.list_tags() if r["name"] == name), None)
        if not row:
            return "対象のタグ名を指定してください。「タグ一覧」で確認できます。"
        if intent == "rename_tag":
            renamed = store.save_tag(str(ai.get("new_tag_name") or ""), row["id"])
            store.write_audit("setting_update_tag", "tag", user["id"], row["id"], before={"name": name}, after={"name": renamed["name"]})
            return f"タグ名を「#{renamed['name']}」に変更しました。チケットとの紐付けは維持されます。"
        store.delete_tag(row["id"])
        store.write_audit("setting_delete_tag", "tag", user["id"], row["id"], before={"name": name})
        return f"タグ「#{name}」を削除しました。"
    return None


def resolve_tag_ids(text: str, ai: dict, store: Any) -> list[str] | None:
    names = ai.get("tag_names")
    if names is None:
        names = re.findall(r"[#＃]([^\s、。]+)", text)
        if not names:
            return None
    if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
        raise ValueError("タグ名を指定してください。")
    known = {r["name"]: r["id"] for r in store.list_tags()}
    normalized = list(dict.fromkeys(n.strip().lstrip("#＃").strip() for n in names))
    unknown = [n for n in normalized if n not in known]
    if unknown:
        raise ValueError(f"未登録のタグ: {', '.join(unknown)}。先に「タグを作成して」と指定するか、設定画面で追加してください。")
    return [known[n] for n in normalized]


def tag_label(ids: list, store: Any) -> str:
    selected = {str(value) for value in ids}
    return " ".join(f"#{r['name']}" for r in store.list_tags() if r["id"] in selected) or "なし"


def patch_tag_ids(current: list, text: str, ai: dict, store: Any) -> list[str]:
    selected = resolve_tag_ids(text, ai, store)
    current = [str(value) for value in current]
    if selected is None:
        return current
    operation = ai.get("tag_operation")
    if operation == "remove":
        return [value for value in current if value not in selected]
    if operation == "add" or (operation is None and re.search(r"追加|付け|つけ", text)):
        return list(dict.fromkeys([*current, *selected]))
    return selected
