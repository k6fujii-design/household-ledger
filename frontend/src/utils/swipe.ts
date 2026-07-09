export type TouchPoint = { x: number; y: number };

export function swipeDirection(start: TouchPoint | null, end: TouchPoint): -1 | 1 | 0 {
  if (!start) return 0;
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  if (Math.abs(dx) < 90) return 0;
  if (Math.abs(dx) < Math.abs(dy) * 2) return 0;
  return dx > 0 ? -1 : 1;
}
