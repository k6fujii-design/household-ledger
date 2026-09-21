import type {
  Tag,
  AgentMemory,
  AppSettings,
  AuditLog,
  CalendarDay,
  CalendarMonthSummary,
  Category,
  MonthlySettlement,
  Summary,
  Ticket,
  TicketInput,
  TicketTemplate,
  TicketTemplateInput,
  User
} from "../types";

const jsonHeaders = { "Content-Type": "application/json" };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: "include", ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "通信に失敗しました");
  }
  return res.json();
}

export const api = {
  tags: () => request<Tag[]>("/api/settings/tags"),
  saveTag: (name: string, id?: string) => request<Tag>(`/api/settings/tags${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", headers: jsonHeaders, body: JSON.stringify({ name }) }),
  deleteTag: (id: string) => request<{ ok: boolean }>(`/api/settings/tags/${id}`, { method: "DELETE" }),
  memories: (scope: "personal" | "shared" = "personal") => request<AgentMemory[]>(`/api/settings/memories?scope=${scope}`),
  saveMemory: (content: string, scope: "personal" | "shared" = "personal") => request<AgentMemory>("/api/settings/memories", { method: "POST", headers: jsonHeaders, body: JSON.stringify({ content, scope }) }),
  deleteMemory: (id: string, scope: "personal" | "shared" = "personal") => request<{ ok: boolean }>(`/api/settings/memories/${id}?scope=${scope}`, { method: "DELETE" }),
  login: (email: string, password: string) =>
    request<{ user: User }>("/api/auth/login", { method: "POST", headers: jsonHeaders, body: JSON.stringify({ email, password }) }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  me: () => request<{ user: User }>("/api/auth/me"),
  users: () => request<User[]>("/api/users"),
  updateUser: (id: string, name: string, lineUserId?: string | null) =>
    request<User>(`/api/users/${id}`, { method: "PUT", headers: jsonHeaders, body: JSON.stringify({ name, line_user_id: lineUserId || null }) }),
  tickets: (params = "") => request<Ticket[]>(`/api/tickets${params}`),
  ticket: (id: string) => request<Ticket>(`/api/tickets/${id}`),
  createTicket: (payload: TicketInput) => request<Ticket>("/api/tickets", { method: "POST", headers: jsonHeaders, body: JSON.stringify(payload) }),
  updateTicket: (id: string, payload: TicketInput) =>
    request<Ticket>(`/api/tickets/${id}`, { method: "PUT", headers: jsonHeaders, body: JSON.stringify(payload) }),
  deleteTicket: (id: string) => request<{ ok: boolean }>(`/api/tickets/${id}`, { method: "DELETE" }),
  summary: (from: string, to: string, statuses = "new,settled", category = "", tagIds: string[] = []) => {
    const params = new URLSearchParams({ from, to, statuses });
    if (tagIds.length) params.set("tag_ids", tagIds.join(","));
    if (category) params.set("category", category);
    return request<Summary>(`/api/reports/summary?${params.toString()}`);
  },
  calendar: (year: number, month: number, statuses = "new,settled", category = "", tagIds: string[] = []) => {
    const params = new URLSearchParams({ year: String(year), month: String(month), statuses });
    if (tagIds.length) params.set("tag_ids", tagIds.join(","));
    if (category) params.set("category", category);
    return request<{ year: number; month: number; days: CalendarDay[] }>(`/api/calendar/month?${params.toString()}`);
  },
  calendarYear: (year: number, statuses = "new,settled", category = "", tagIds: string[] = []) => {
    const params = new URLSearchParams({ year: String(year), statuses });
    if (tagIds.length) params.set("tag_ids", tagIds.join(","));
    if (category) params.set("category", category);
    return request<{ year: number; months: CalendarMonthSummary[] }>(`/api/calendar/year?${params.toString()}`);
  },
  bulkStatus: (from: string, to: string) =>
    request<{ updated_count: number; to_status: string }>("/api/tickets/bulk-status", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ from, to, from_status: "new", to_status: "settled" })
    }),
  bulkAddTags: (ticketIds: string[], tagIds: string[]) =>
    request<{ updated_count: number; ticket_ids: string[] }>("/api/tickets/bulk-tags", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ ticket_ids: ticketIds, tag_ids: tagIds })
    }),
  settings: () => request<AppSettings>("/api/settings"),
  updateSettings: (payload: AppSettings) => request<AppSettings>("/api/settings", { method: "PUT", headers: jsonHeaders, body: JSON.stringify(payload) }),
  categories: () => request<Category[]>("/api/settings/categories"),
  createCategory: (payload: Omit<Category, "id">) =>
    request<Category>("/api/settings/categories", { method: "POST", headers: jsonHeaders, body: JSON.stringify(payload) }),
  updateCategory: (id: string, payload: Omit<Category, "id">) =>
    request<Category>(`/api/settings/categories/${id}`, { method: "PUT", headers: jsonHeaders, body: JSON.stringify(payload) }),
  deleteCategory: (id: string) => request<{ ok: boolean }>(`/api/settings/categories/${id}`, { method: "DELETE" }),
  templates: () => request<TicketTemplate[]>("/api/settings/templates"),
  createTemplate: (payload: TicketTemplateInput) =>
    request<TicketTemplate>("/api/settings/templates", { method: "POST", headers: jsonHeaders, body: JSON.stringify(payload) }),
  updateTemplate: (id: string, payload: TicketTemplateInput) =>
    request<TicketTemplate>(`/api/settings/templates/${id}`, { method: "PUT", headers: jsonHeaders, body: JSON.stringify(payload) }),
  deleteTemplate: (id: string) => request<{ ok: boolean }>(`/api/settings/templates/${id}`, { method: "DELETE" }),
  monthlySettlement: (periodKey: string) => request<MonthlySettlement>(`/api/settings/monthly-settlements/${periodKey}`),
  updateMonthlySettlement: (periodKey: string, payload: Omit<MonthlySettlement, "period_key">) =>
    request<MonthlySettlement>(`/api/settings/monthly-settlements/${periodKey}`, { method: "PUT", headers: jsonHeaders, body: JSON.stringify(payload) }),
  auditLogs: (limit = 100) => request<AuditLog[]>(`/api/audit-logs?limit=${limit}`)
};
