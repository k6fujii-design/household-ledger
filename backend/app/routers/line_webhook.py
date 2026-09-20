from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import urllib.error
import urllib.request
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.core.secrets import line_channel_access_token, line_channel_secret
from app.services.line_agent import get_ticket_draft_editor, handle_line_text, update_ticket_draft_from_editor
from app.services.agent_preferences import tag_label
from app.store import DynamoStore, get_store

router = APIRouter(prefix="/line", tags=["line"])
logger = logging.getLogger(__name__)


def _draft_editor_html(
    token: str,
    editor: dict[str, object],
    *,
    saved: bool = False,
    error: str | None = None,
) -> str:
    payload = dict(editor["payload"])
    users = list(editor["users"])
    categories = list(editor["categories"])
    current_payer = str(payload.get("payer_user_id") or "")
    current_category = str(payload.get("category") or "")
    current_status = str(payload.get("status") or "new")
    tag_options = "".join(
        f'<label><input type="checkbox" name="tag_ids" value="{html.escape(str(row["id"]))}"'
        + (' checked' if str(row["id"]) in payload.get("tag_ids", []) else '')
        + f'> #{html.escape(str(row["name"]))}</label>'
        for row in editor.get("tags", [])
    )
    ratio_f = int(payload.get("ratio_f") or 0)

    def option(value: str, label: str, selected: str) -> str:
        selected_attr = " selected" if value == selected else ""
        return f'<option value="{html.escape(value)}"{selected_attr}>{html.escape(label)}</option>'

    category_options = option("", "未指定", current_category) + "".join(
        option(str(row["name"]), str(row["name"]), current_category)
        for row in categories
    )
    payer_options = "".join(
        option(str(row["id"]), str(row["name"]), current_payer)
        for row in users
    )
    user_by_email = {str(row.get("email")): str(row.get("name")) for row in users}
    ratio_f_name = user_by_email.get("f@example.com", "User 1")
    ratio_o_name = user_by_email.get("o@example.com", "User 2")
    status_options = "".join([
        option("new", "未精算", current_status),
        option("settled", "精算済み", current_status),
        option("canceled", "取り消し", current_status),
    ])
    notice = ""
    if saved:
        notice = '<div class="notice success" role="status">変更を保存しました。画面上部の×（閉じる）でLINEに戻り、変更後の内容を確認して「登録する」を押してください。まだチケットの登録は完了していません。</div>'
    elif error:
        notice = f'<div class="notice error">{html.escape(error)}</div>'

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>チケット登録内容の修正</title>
  <style>
    :root {{ color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #fff8f1; color: #322c28; }}
    main {{ width: min(100%, 560px); margin: 0 auto; padding: 24px 18px 40px; }}
    h1 {{ margin: 0 0 6px; font-size: 22px; letter-spacing: 0; }}
    .lead {{ margin: 0 0 20px; color: #776d65; font-size: 14px; }}
    form {{ background: #fff; border: 1px solid #eadfd5; border-radius: 8px; padding: 18px; box-shadow: 0 8px 24px rgba(87, 65, 48, .08); }}
    label {{ display: block; margin: 0 0 15px; font-size: 13px; font-weight: 700; color: #5c5149; }}
    input, select, textarea {{ display: block; width: 100%; min-width: 0; max-width: 100%; margin-top: 7px; border: 1px solid #d8c9bd; border-radius: 6px; background: #fff; color: #322c28; padding: 11px 12px; font: inherit; font-size: 16px; }}
    input[type=date] {{ appearance: none; -webkit-appearance: none; min-height: 46px; }}
    input[type=date]::-webkit-date-and-time-value {{ min-width: 0; text-align: left; }}
    textarea {{ min-height: 82px; resize: vertical; }}
    input:focus, select:focus, textarea:focus {{ border-color: #de8754; outline: 3px solid #fbe3d3; }}
    input[type="range"] {{ padding: 7px 0; accent-color: #df8050; }}
    input[type="checkbox"] {{ display: inline-block; width: auto; margin: 0; }}
    fieldset {{ border: 0; padding: 0; margin: 12px 0; }}
    .ratio {{ display: flex; justify-content: space-between; gap: 12px; margin-top: 2px; color: #776d65; font-size: 13px; font-weight: 600; }}
    .notice {{ margin-bottom: 16px; border-radius: 6px; padding: 12px; font-size: 14px; }}
    .success {{ background: #edf7ef; color: #27623a; }}
    .error {{ background: #fff0ed; color: #9a3e32; }}
    button {{ display: flex; align-items: center; justify-content: center; width: 100%; min-height: 48px; border: 0; border-radius: 6px; font-size: 16px; font-weight: 800; }}
    button {{ background: #df8050; color: #fff; cursor: pointer; }}
    .hint {{ margin: 14px 2px 0; color: #887c73; font-size: 12px; line-height: 1.6; }}
  </style>
</head>
<body>
<main>
  <h1>チケット登録内容の修正</h1>
  <p class="lead">変更したい項目だけ直して保存できます。</p>
  {notice}
  <form method="post">
    <label>件名<input name="title" required maxlength="160" value="{html.escape(str(payload.get('title') or ''))}"></label>
    <label>日付<input type="date" name="date" required value="{html.escape(str(payload.get('date') or ''))}"></label>
    <label>金額<input type="number" name="amount" required min="1" step="1" inputmode="numeric" value="{html.escape(str(payload.get('amount') or ''))}"></label>
    <label>カテゴリ<select name="category">{category_options}</select></label>
    <fieldset><legend>タグ</legend>{tag_options}</fieldset>
    <label>立替者<select name="payer_user_id" required>{payer_options}</select></label>
    <label>負担比率
      <input id="ratio" type="range" name="ratio_f" min="0" max="10" step="1" value="{ratio_f}">
      <span class="ratio"><span id="ratio-f"></span><span id="ratio-o"></span></span>
    </label>
    <label>ステータス<select name="status" required>{status_options}</select></label>
    <label>メモ<textarea name="memo" maxlength="1000">{html.escape(str(payload.get('memo') or ''))}</textarea></label>
    <button type="submit">変更を保存</button>
  </form>
  <p class="hint">保存した後は、画面上部の×（閉じる）でLINEに戻ってください。外部ブラウザで開いた場合はLINEアプリに切り替えてください。このリンクは短時間だけ有効です。</p>
</main>
<script>
  const slider = document.getElementById('ratio');
  const left = document.getElementById('ratio-f');
  const right = document.getElementById('ratio-o');
  function renderRatio() {{
    const value = Number(slider.value);
    left.textContent = '{html.escape(ratio_f_name)} ' + (value * 10) + '%';
    right.textContent = '{html.escape(ratio_o_name)} ' + ((10 - value) * 10) + '%';
  }}
  slider.addEventListener('input', renderRatio);
  renderRatio();
</script>
</body>
</html>"""


def _html_response(content: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        content,
        status_code=status_code,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'",
        },
    )


def _line_user_hash(line_user_id: str | None) -> str | None:
    if not line_user_id:
        return None
    return hashlib.sha256(line_user_id.encode("utf-8")).hexdigest()[:12]


def _line_text_message(text: str, quick_replies: list[str] | None = None) -> dict[str, object]:
    message: dict[str, object] = {"type": "text", "text": text[:5000]}
    if quick_replies:
        message["quickReply"] = {
            "items": [
                {
                    "type": "action",
                    "action": {"type": "message", "label": label[:20], "text": label},
                }
                for label in quick_replies[:13]
            ]
        }
    return message


def push_message(line_user_id: str, text: str, quick_replies: list[str] | None = None) -> None:
    token = line_channel_access_token()
    if not token:
        logger.error("line_push_token_not_configured", extra={"event": "line_push_token_not_configured"})
        return
    payload = json.dumps({"to": line_user_id, "messages": [_line_text_message(text, quick_replies)]}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=payload,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=8).read()
        logger.info("line_push_sent", extra={"event": "line_push_sent", "line_user_hash": _line_user_hash(line_user_id)})
    except urllib.error.URLError:
        logger.exception("line_push_failed", extra={"event": "line_push_failed", "line_user_hash": _line_user_hash(line_user_id)})


def verify_signature(body: bytes, signature: str | None, secret: str) -> None:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid LINE signature")


@router.get("/draft/{token}", response_class=HTMLResponse)
def ticket_draft_editor(token: str, store: DynamoStore = Depends(get_store)):
    editor = get_ticket_draft_editor(store, token)
    if not editor:
        return _html_response(
            "<!doctype html><html lang='ja'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            "<body style='font-family:sans-serif;padding:24px;background:#fff8f1;color:#322c28'>"
            "<h1 style='font-size:21px'>編集リンクを利用できません</h1>"
            "<p>有効期限が切れたか、登録・キャンセル済みです。LINEからもう一度操作してください。</p></body></html>",
            status_code=410,
        )
    return _html_response(_draft_editor_html(token, editor))


@router.post("/draft/{token}", response_class=HTMLResponse)
async def save_ticket_draft_editor(token: str, request: Request, store: DynamoStore = Depends(get_store)):
    form = await request.form()
    values = {key: str(value) for key, value in form.items()}
    values["tag_ids"] = [str(value) for value in form.getlist("tag_ids")]
    try:
        payload, context = update_ticket_draft_from_editor(store, token, values)
    except (TypeError, ValueError) as exc:
        editor = get_ticket_draft_editor(store, token)
        if not editor:
            return _html_response(
                "<!doctype html><html lang='ja'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                "<body style='font-family:sans-serif;padding:24px;background:#fff8f1;color:#322c28'>"
                "<h1 style='font-size:21px'>編集リンクを利用できません</h1>"
                "<p>有効期限が切れました。LINEからもう一度操作してください。</p></body></html>",
                status_code=410,
            )
        return _html_response(_draft_editor_html(token, editor, error=str(exc)), status_code=400)

    editor = {"payload": payload.model_dump(mode="json"), **context}
    payer_name = next(
        (str(row["name"]) for row in context["users"] if str(row["id"]) == str(payload.payer_user_id)),
        "-",
    )
    push_message(
        str(context["line_user_id"]),
        "変更後の内容です。\n"
        f"件名: {payload.title}\n"
        f"日付: {payload.date.isoformat()}\n"
        f"金額: {payload.amount:,}円\n"
        f"カテゴリ: {payload.category or '未指定'}\n"
        f"タグ: {tag_label(payload.tag_ids, store)}\n"
        f"立替: {payer_name}\n"
        f"負担比率: {payload.ratio_f * 10}% / {payload.ratio_o * 10}%\n\n"
        "この内容で登録しますか？",
        ["登録する", "やめる"],
    )
    return _html_response(_draft_editor_html(token, editor, saved=True))


def reply_message(
    reply_token: str,
    text: str,
    quick_replies: list[str] | None = None,
    request_id: str | None = None,
    preface: str | None = None,
) -> None:
    token = line_channel_access_token()
    if not token:
        logger.error("line_reply_token_not_configured", extra={"event": "line_reply_token_not_configured", "request_id": request_id})
        return

    message = _line_text_message(text, quick_replies)

    messages: list[dict[str, object]] = []
    if preface:
        messages.append({"type": "text", "text": preface[:5000]})
    messages.append(message)
    payload = json.dumps({"replyToken": reply_token, "messages": messages[:5]}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/reply",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=8).read()
        logger.info("line_reply_sent", extra={"event": "line_reply_sent", "request_id": request_id})
    except urllib.error.URLError:
        logger.exception("line_reply_failed", extra={"event": "line_reply_failed", "request_id": request_id})
        return


@router.post("/webhook")
async def line_webhook(request: Request, store: DynamoStore = Depends(get_store)):
    body = await request.body()
    secret = line_channel_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="LINE channel secret is not configured")
    verify_signature(body, request.headers.get("x-line-signature"), secret)

    payload = json.loads(body.decode("utf-8"))
    for event in payload.get("events", []):
        request_id = event.get("webhookEventId") or str(uuid4())
        if event.get("type") != "message" or event.get("message", {}).get("type") != "text":
            continue
        reply_token = event.get("replyToken")
        line_user_id = event.get("source", {}).get("userId")
        text = event.get("message", {}).get("text", "")
        logger.info(
            "line_message_received",
            extra={
                "event": "line_message_received",
                "request_id": request_id,
                "line_user_hash": _line_user_hash(line_user_id),
                "details": {"message_length": len(text)},
            },
        )
        if not reply_token:
            logger.warning("line_reply_token_missing", extra={"event": "line_reply_token_missing", "request_id": request_id})
            continue
        if not line_user_id:
            reply_message(reply_token, "LINE\u30e6\u30fc\u30b6\u30fcID\u3092\u53d6\u5f97\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f\u3002", request_id=request_id)
            continue

        app_user = store.get_user_by_line_user_id(line_user_id)
        if not app_user:
            logger.warning(
                "line_user_not_registered",
                extra={"event": "line_user_not_registered", "request_id": request_id, "line_user_hash": _line_user_hash(line_user_id)},
            )
            reply_message(
                reply_token,
                "\u3053\u306eLINE\u30e6\u30fc\u30b6\u30fcID\u306f\u5bb6\u8a08\u7c3f\u30a2\u30d7\u30ea\u306b\u767b\u9332\u3055\u308c\u3066\u3044\u307e\u305b\u3093\u3002\n"
                f"LINE\u30e6\u30fc\u30b6\u30fcID:\n{line_user_id}\n"
                "Web\u30a2\u30d7\u30ea\u306e\u300c\u8a2d\u5b9a\u300d>\u300c\u30e6\u30fc\u30b6\u30fc\u8a2d\u5b9a\u300d\u304b\u3089LINE\u30e6\u30fc\u30b6\u30fcID\u3092\u767b\u9332\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                request_id=request_id,
            )
            continue

        try:
            result = handle_line_text(
                text,
                line_user_id,
                app_user,
                store,
                request_id=request_id,
                public_base_url=str(request.base_url).rstrip("/"),
            )
            reply_message(
                reply_token,
                result.reply,
                result.quick_replies,
                request_id=request_id,
                preface=result.preface,
            )
        except Exception:
            logger.exception(
                "line_message_processing_failed",
                extra={
                    "event": "line_message_processing_failed",
                    "request_id": request_id,
                    "line_user_hash": _line_user_hash(line_user_id),
                    "user_id": app_user.get("id"),
                },
            )
            reply_message(reply_token, "処理中にエラーが発生しました。時間をおいてもう一度お試しください。", request_id=request_id)

    return {"ok": True}
