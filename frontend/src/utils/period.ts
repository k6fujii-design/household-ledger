export function currentPeriod(closingDay: number, base = new Date()) {
  const year = base.getFullYear();
  const month = base.getMonth();
  const day = base.getDate();
  if (closingDay >= 28) {
    const from = new Date(year, month, 1);
    const to = new Date(year, month + 1, 0);
    return toPeriod(from, to);
  }
  const toMonth = day <= closingDay ? month : month + 1;
  const from = new Date(year, toMonth - 1, closingDay + 1);
  const to = new Date(year, toMonth, closingDay);
  return toPeriod(from, to);
}

export function periodKey(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

export function monthLabel(date: Date) {
  return `${date.getFullYear()}年${date.getMonth() + 1}月`;
}

export function addMonths(date: Date, diff: number) {
  return new Date(date.getFullYear(), date.getMonth() + diff, 1);
}

function toPeriod(from: Date, to: Date) {
  return {
    from: toDateInput(from),
    to: toDateInput(to),
    key: periodKey(to)
  };
}

function toDateInput(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
