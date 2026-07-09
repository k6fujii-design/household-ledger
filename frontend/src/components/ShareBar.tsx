import type { CSSProperties } from "react";
import type { User } from "../types";
import { formatYen, userPair } from "../utils/display";

export function ShareBar({
  users,
  ratioF,
  ratioO,
  amountF,
  amountO,
  compact = false,
  percent = false
}: {
  users: User[];
  ratioF: number;
  ratioO: number;
  amountF?: number;
  amountO?: number;
  compact?: boolean;
  percent?: boolean;
}) {
  const pair = userPair(users);
  const total = ratioF + ratioO || 1;
  const firstWidth = Math.max(0, Math.min(100, (ratioF / total) * 100));
  const formatShare = (ratio: number, amount?: number) => {
    const value = percent ? `${Math.round((ratio / total) * 100)}%` : String(ratio);
    return `${value}${amount !== undefined ? ` / ${formatYen(amount)}` : ""}`;
  };

  return (
    <div className={`${compact ? "share-bar compact" : "share-bar"}${percent ? " percent" : ""}`}>
      <div className="share-track" style={{ "--first-width": `${firstWidth}%` } as CSSProperties} />
      <div className="share-labels">
        <span>{pair.first} {formatShare(ratioF, amountF)}</span>
        <span>{pair.second} {formatShare(ratioO, amountO)}</span>
      </div>
    </div>
  );
}
