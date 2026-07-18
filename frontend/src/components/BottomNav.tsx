import { CalendarDays, CirclePlus, Home, PieChart, Settings } from "lucide-react";
import type { View } from "../App";

const items: { view: View; label: string; Icon: any; special?: boolean }[] = [
  { view: "home", label: "ホーム", Icon: Home },
  { view: "summary", label: "集計", Icon: PieChart },
  { view: "create", label: "追加", Icon: CirclePlus, special: true },
  { view: "calendar", label: "カレンダー", Icon: CalendarDays },
  { view: "settings", label: "設定", Icon: Settings }
];

export function BottomNav({ view, setView }: { view: View; setView: (view: View) => void }) {
  return (
    <nav className="bottom-nav">
      {items.map(({ view: target, label, Icon, special }) => (
        <button key={target} className={`${view === target ? "active" : ""}${special ? " nav-create" : ""}`} onClick={() => setView(target)} title={label} aria-label={label}>
          <Icon size={special ? 36 : 18} />
          {!special && <span>{label}</span>}
        </button>
      ))}
    </nav>
  );
}
