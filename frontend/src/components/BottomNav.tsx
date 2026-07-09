import { CalendarDays, CirclePlus, Home, PieChart, Settings } from "lucide-react";
import type { View } from "../App";

const items: { view: View; label: string; Icon: any }[] = [
  { view: "home", label: "ホーム", Icon: Home },
  { view: "summary", label: "集計", Icon: PieChart },
  { view: "create", label: "記録", Icon: CirclePlus },
  { view: "calendar", label: "カレンダー", Icon: CalendarDays },
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
