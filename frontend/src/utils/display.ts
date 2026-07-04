import type { User } from "../types";

export const yen = new Intl.NumberFormat("ja-JP");

export function formatYen(amount: number): string {
  return `${yen.format(amount)}円`;
}

export function compactYen(amount: number): string {
  if (amount === 0) return "0円";
  if (amount % 10000 === 0) return `${amount / 10000}万円`;
  if (amount >= 10000) {
    const man = Math.floor(amount / 10000);
    const rest = amount % 10000;
    if (rest === 0) return `${man}万円`;
    if (rest % 1000 === 0) return `${man}万${rest / 1000}千円`;
    return `${man}万円`;
  }
  if (amount % 1000 === 0) return `${amount / 1000}千円`;
  return `${yen.format(amount)}円`;
}

export function userPair(users: User[]) {
  return {
    first: users[0]?.name || "User 1",
    second: users[1]?.name || "User 2"
  };
}

export const statusLabels = {
  new: "未精算",
  settled: "精算済み",
  canceled: "取り消し"
} as const;
