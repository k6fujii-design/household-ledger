import {
  Gamepad2,
  HeartPulse,
  House,
  LucideIcon,
  Shapes,
  ShoppingBasket,
  Smartphone,
  Sparkles,
  Tag,
  TrainFront,
  Utensils,
  UtensilsCrossed,
  Zap
} from "lucide-react";
import type { Category } from "../types";

const icons: Record<string, LucideIcon> = {
  utensils: Utensils,
  restaurant: UtensilsCrossed,
  "shopping-basket": ShoppingBasket,
  house: House,
  zap: Zap,
  smartphone: Smartphone,
  train: TrainFront,
  "heart-pulse": HeartPulse,
  sparkles: Sparkles,
  gamepad: Gamepad2,
  shapes: Shapes,
  tag: Tag
};

const defaultIconByName: Record<string, string> = {
  "食費": "utensils", "外食": "restaurant", "日用品": "shopping-basket", "住居": "house",
  "水道・光熱費": "zap", "通信費": "smartphone", "交通費": "train", "医療・健康": "heart-pulse",
  "衣服・美容": "sparkles", "娯楽・趣味": "gamepad", "その他": "shapes"
};

const iconRules: Array<[RegExp, string]> = [
  [/外食|レストラン|カフェ|デリバリー/, "restaurant"],
  [/食費|食品|食材|飲料|スーパー|コンビニ/, "utensils"],
  [/日用品|生活雑貨|洗剤/, "shopping-basket"],
  [/住居|家賃|家具/, "house"],
  [/水道|光熱|電気|ガス/, "zap"],
  [/通信|スマホ|インターネット|郵送/, "smartphone"],
  [/交通|電車|バス|タクシー|ガソリン/, "train"],
  [/医療|健康|病院|薬|ジム/, "heart-pulse"],
  [/衣服|美容|化粧|服|靴/, "sparkles"],
  [/娯楽|趣味|ゲーム|映画|旅行|サブスク/, "gamepad"],
  [/その他/, "shapes"]
];

const customIconNames = ["shapes", "sparkles", "gamepad", "shopping-basket", "house", "train", "heart-pulse", "zap", "smartphone"];

function inferredIconName(category?: Category) {
  const name = category?.name || "";
  if (category?.icon && category.icon !== "tag") return category.icon;
  if (defaultIconByName[name]) return defaultIconByName[name];
  const matched = iconRules.find(([pattern]) => pattern.test(name));
  if (matched) return matched[1];
  if (!name) return "tag";
  const hash = [...name].reduce((sum, character) => sum + (character.codePointAt(0) || 0), 0);
  return customIconNames[hash % customIconNames.length];
}

export function categoryForName(categories: Category[], name: string) {
  return categories.find((category) => category.name === name);
}

export function CategoryIcon({ category, size = 18, className = "" }: { category?: Category; size?: number; className?: string }) {
  const iconName = inferredIconName(category);
  const Icon = icons[iconName] || Tag;
  const color = category?.color || "#94a3b8";
  return (
    <span className={`category-icon ${className}`} style={{ color, backgroundColor: `${color}18` }} aria-hidden="true">
      <Icon size={size} strokeWidth={2.2} />
    </span>
  );
}
