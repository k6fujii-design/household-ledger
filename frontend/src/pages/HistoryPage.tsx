import { Bot, ExternalLink, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AuditLog } from "../types";

const actionLabels: Record<string, string> = {
  ticket_create: "\u30c1\u30b1\u30c3\u30c8\u4f5c\u6210",
  ticket_update: "\u30c1\u30b1\u30c3\u30c8\u7de8\u96c6",
  ticket_delete: "\u30c1\u30b1\u30c3\u30c8\u524a\u9664",
  ticket_status_change: "\u30b9\u30c6\u30fc\u30bf\u30b9\u5909\u66f4",
  ticket_bulk_status_update: "\u4e00\u62ec\u7cbe\u7b97",
  setting_update_user_name: "\u8868\u793a\u540d\u5909\u66f4",
  setting_update_closing_day: "\u7de0\u3081\u65e5\u5909\u66f4",
  setting_create_category: "\u30ab\u30c6\u30b4\u30ea\u8ffd\u52a0",
  setting_update_category: "\u30ab\u30c6\u30b4\u30ea\u7de8\u96c6",
  setting_delete_category: "\u30ab\u30c6\u30b4\u30ea\u524a\u9664",
  setting_create_template: "\u30c6\u30f3\u30d7\u30ec\u30fc\u30c8\u8ffd\u52a0",
  setting_update_template: "\u30c6\u30f3\u30d7\u30ec\u30fc\u30c8\u7de8\u96c6",
  setting_delete_template: "\u30c6\u30f3\u30d7\u30ec\u30fc\u30c8\u524a\u9664",
  setting_update_monthly_settlement: "\u6708\u6b21\u30e1\u30e2\u66f4\u65b0",
  ai_tool_call: "AI\u51e6\u7406\u30ed\u30b0",
};

const toolLabels: Record<string, string> = {
  create_ticket: "\u30c1\u30b1\u30c3\u30c8\u4f5c\u6210",
  ask_missing_amount: "\u4e0d\u8db3\u9805\u76ee\u306e\u805e\u304d\u8fd4\u3057",
  answer_summary: "\u96c6\u8a08\u30fb\u50be\u5411\u5206\u6790",
  update_ticket: "\u30c1\u30b1\u30c3\u30c8\u66f4\u65b0",
  delete_ticket: "\u30c1\u30b1\u30c3\u30c8\u524a\u9664",
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
  if (typeof after.updated_count === "number") return `${after.updated_count}\u4ef6`;
  return log.target_type;
}

function canOpenTicket(log: AuditLog) {
  return Boolean(log.target_id && log.target_type === "ticket" && log.action !== "ticket_bulk_status_update" && log.action !== "ticket_delete");
}

function traceItems(log: AuditLog) {
  const trace = log.after?.trace;
  return Array.isArray(trace) ? trace.filter((item): item is string => typeof item === "string") : [];
}

function AiLogCard({ log }: { log: AuditLog }) {
  const tool = typeof log.after?.tool === "string" ? log.after.tool : "";
  const result = log.after?.result && typeof log.after.result === "object" ? log.after.result as Record<string, unknown> : {};
  return (
    <article className="history-item history-ai">
      <div className="history-ai-head">
        <span className="history-ai-icon"><Bot size={16} /></span>
        <div>
          <strong>{actionLabels.ai_tool_call}</strong>
          <span>{toolLabels[tool] || tool || "\u30c4\u30fc\u30eb\u5b9f\u884c"}</span>
        </div>
      </div>
      {traceItems(log).length > 0 && (
        <ul className="history-ai-trace">
          {traceItems(log).slice(0, 5).map((item) => <li key={item}>{item}</li>)}
        </ul>
      )}
      {typeof result.display_id === "number" && <small>\u30c1\u30b1\u30c3\u30c8ID: {result.display_id}</small>}
      <div className="history-meta">
        <span>{log.actor_name || "LINE Bot"}</span>
        <time>{new Date(log.created_at).toLocaleString("ja-JP")}</time>
      </div>
    </article>
  );
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
        <h1>\u5c65\u6b74</h1>
        <button onClick={load}><RefreshCw size={18} />\u66f4\u65b0</button>
      </header>
      {loading && <div className="muted">\u8aad\u307f\u8fbc\u307f\u4e2d...</div>}
      <div className="history-list">
        {logs.filter((log) => !hiddenActions.has(log.action)).map((log) => {
          if (log.action === "ai_tool_call") {
            return <AiLogCard key={log.id} log={log} />;
          }

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
