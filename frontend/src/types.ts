export type User = { id: string; name: string; email: string };

export type TicketStatus = "new" | "settled" | "canceled";

export type Ticket = {
  id: string;
  date: string;
  title: string;
  amount: number;
  payer_user_id: string;
  payer_name?: string;
  ratio_f: number;
  ratio_o: number;
  share_f: number;
  share_o: number;
  status: TicketStatus;
  category: string;
  memo: string;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type TicketInput = {
  date: string;
  title: string;
  amount: number;
  payer_user_id: string;
  ratio_f: number;
  ratio_o: number;
  status: TicketStatus;
  category: string;
  memo: string;
};

export type Summary = {
  from_: string;
  to: string;
  total_amount: number;
  ticket_count: number;
  paid_by_f: number;
  paid_by_o: number;
  share_f: number;
  share_o: number;
  balance_f: number;
  balance_o: number;
  settlement: { from_user: string | null; to_user: string | null; amount: number };
};

export type CalendarDay = {
  date: string;
  total_amount: number;
  ticket_count: number;
  paid_by_f: number;
  paid_by_o: number;
};

export type CalendarMonthSummary = {
  month: number;
  total_amount: number;
  ticket_count: number;
  paid_by_f: number;
  paid_by_o: number;
};

export type Category = {
  id: string;
  name: string;
  color: string;
};

export type TicketTemplate = {
  id: string;
  name: string;
  title: string;
  amount: number;
  payer_user_id: string | null;
  ratio_f: number;
  ratio_o: number;
  status: TicketStatus;
  category: string;
  memo: string;
};

export type TicketTemplateInput = Omit<TicketTemplate, "id">;

export type AppSettings = {
  closing_day: number;
};

export type MonthlySettlement = {
  period_key: string;
  status: string;
  memo: string;
  closing_day: number;
};

export type AuditLog = {
  id: string;
  actor_user_id: string | null;
  actor_name?: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
};
