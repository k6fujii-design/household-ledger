import { ExternalLink, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AuditLog } from "../types";

const actionLabels: Record<string, string> = {
  ticket_create: "チケット作成",
  ticket_update: "チケット編集",
  ticket_delete: "チケット削除",
  ticket_status_change: "ステータス変更",
  ticket_bulk_status_update: "一括精算",
  setting_update_user_name: "表示名変更",
  setting_update_closing_day: "締め日変更",
  setting_create_category: "カテゴリ追加",
  setting_update_category: "カテゴリ編集",
  setting_delete_category: "カテゴリ削除",
  setting_create_template: "テンプレート追加",
  setting_update_template: "テンプレート編集",
  setting_delete_template: "テンプレート削除",
  setting_update_monthly_settlement: "月次メモ更新"
};

const hiddenActions = new Set(["login_success", "login_failure", "logout"]);

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

function canOpenTicket(log: AuditLog) {
  return Boolean(log.target_id && log.target_type === "ticket" && log.action !== "ticket_bulk_status_update" && log.action !== "ticket_delete");
}

export function HistoryPage({ openEdit }: { openEdit: (id: string) => void }) {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      setLogs(await api.auditLogs(150));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <main className="screen">
      <header className="top">
        <h1>履歴</h1>
        <button onClick={load}><RefreshCw size={18} />更新</button>
      </header>
      {loading && <div className="muted">読み込み中...</div>}
      <div className="history-list">
        {logs.filter((log) => !hiddenActions.has(log.action)).map((log) => {
          const content = (
            <>
              <div>
                <strong>{actionLabels[log.action] || log.action}</strong>
                <span>{describe(log)}</span>
              </div>
              <div className="history-meta">
                <span>{log.actor_name || "system"}</span>
                <time>{new Date(log.created_at).toLocaleString("ja-JP")}</time>
              </div>
            </>
          );

          if (canOpenTicket(log)) {
            return (
              <button key={log.id} className="history-item history-link" onClick={() => openEdit(log.target_id!)}>
                <span className="history-link-body">{content}</span>
                <ExternalLink size={16} />
              </button>
            );
          }

          return <article key={log.id} className="history-item">{content}</article>;
        })}
      </div>
    </main>
  );
}
