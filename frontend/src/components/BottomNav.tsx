import { CalendarDays, History, Home, ListChecks, PieChart, Settings } from "lucide-react";
import type { View } from "../App";

const items: { view: View; label: string; Icon: any }[] = [
  { view: "home", label: "ホーム", Icon: Home },
  { view: "tickets", label: "チケット", Icon: ListChecks },
  { view: "summary", label: "集計", Icon: PieChart },
  { view: "calendar", label: "カレンダー", Icon: CalendarDays },
  { view: "history", label: "履歴", Icon: History },
  { view: "settings", label: "設定", Icon: Settings }
];

export function BottomNav({ view, setView }: { view: View; setView: (view: View) => void }) {
  return (
    <nav className="bottom-nav">
      {items.map(({ view: target, label, Icon }) => (
        <button key={target} className={view === target ? "active" : ""} onClick={() => setView(target)} title={label}>
          <Icon size={18} />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
