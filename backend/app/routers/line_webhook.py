from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.secrets import line_channel_access_token, line_channel_secret
from app.services.line_agent import handle_line_text
from app.store import DynamoStore, get_store

router = APIRouter(prefix="/line", tags=["line"])


def verify_signature(body: bytes, signature: str | None, secret: str) -> None:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid LINE signature")


def reply_message(reply_token: str, text: str, quick_replies: list[str] | None = None) -> None:
    token = line_channel_access_token()
    if not token:
        return

    message: dict[str, object] = {"type": "text", "text": text[:5000]}
    if quick_replies:
        message["quickReply"] = {
            "items": [
                {
                    "type": "action",
                    "action": {
                        "type": "message",
                        "label": label[:20],
                        "text": label,
                    },
                }
                for label in quick_replies[:13]
            ]
        }

    payload = json.dumps({"replyToken": reply_token, "messages": [message]}).encode("utf-8")
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
    except urllib.error.URLError:
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
        if event.get("type") != "message" or event.get("message", {}).get("type") != "text":
            continue
        reply_token = event.get("replyToken")
        line_user_id = event.get("source", {}).get("userId")
        text = event.get("message", {}).get("text", "")
        if not reply_token:
            continue
        if not line_user_id:
            reply_message(reply_token, "LINE\u30e6\u30fc\u30b6\u30fcID\u3092\u53d6\u5f97\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f\u3002")
            continue

        app_user = store.get_user_by_line_user_id(line_user_id)
        if not app_user:
            reply_message(
                reply_token,
                "\u3053\u306eLINE\u30e6\u30fc\u30b6\u30fcID\u306f\u5bb6\u8a08\u7c3f\u30a2\u30d7\u30ea\u306b\u767b\u9332\u3055\u308c\u3066\u3044\u307e\u305b\u3093\u3002\n"
                f"LINE\u30e6\u30fc\u30b6\u30fcID:\n{line_user_id}\n"
                "Web\u30a2\u30d7\u30ea\u306e\u300c\u8a2d\u5b9a\u300d>\u300c\u30e6\u30fc\u30b6\u30fc\u8a2d\u5b9a\u300d\u304b\u3089LINE\u30e6\u30fc\u30b6\u30fcID\u3092\u767b\u9332\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
            )
            continue

        result = handle_line_text(text, line_user_id, app_user, store)
        reply_message(reply_token, result.reply, result.quick_replies)

    return {"ok": True}
