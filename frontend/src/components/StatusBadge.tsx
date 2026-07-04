import type { TicketStatus } from "../types";
import { statusLabels } from "../utils/display";

export function StatusBadge({ status }: { status: TicketStatus }) {
  return <span className={`status status-${status}`}>{statusLabels[status]}</span>;
}
