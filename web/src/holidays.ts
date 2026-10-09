export const isoDay = (d: Date) =>
  d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");

function nth(year: number, month: number, weekday: number, n: number) {
  if (n > 0) {
    const shift = (weekday - new Date(year, month, 1).getDay() + 7) % 7;
    return new Date(year, month, 1 + shift + (n - 1) * 7);
  }
  const last = new Date(year, month + 1, 0);
  return new Date(year, month, last.getDate() - ((last.getDay() - weekday + 7) % 7));
}

const cache = new Map<number, Map<string, string>>();

export function holidays(year: number): Map<string, string> {
  const hit = cache.get(year);
  if (hit) return hit;
  const out = new Map<string, string>();
  const fixed = (month: number, day: number, name: string) => {
    const d = new Date(year, month, day);
    out.set(isoDay(d), name);
    if (d.getDay() === 6) out.set(isoDay(new Date(year, month, day - 1)), name + " (observed)");
    if (d.getDay() === 0) out.set(isoDay(new Date(year, month, day + 1)), name + " (observed)");
  };
  fixed(0, 1, "New Year's Day");
  out.set(isoDay(nth(year, 0, 1, 3)), "Martin Luther King Jr. Day");
  out.set(isoDay(nth(year, 1, 1, 3)), "Presidents' Day");
  out.set(isoDay(nth(year, 4, 1, -1)), "Memorial Day");
  fixed(5, 19, "Juneteenth");
  fixed(6, 4, "Independence Day");
  out.set(isoDay(nth(year, 8, 1, 1)), "Labor Day");
  out.set(isoDay(nth(year, 9, 1, 2)), "Indigenous Peoples' Day");
  fixed(10, 11, "Veterans Day");
  const thanks = nth(year, 10, 4, 4);
  out.set(isoDay(thanks), "Thanksgiving");
  out.set(isoDay(new Date(year, 10, thanks.getDate() + 1)), "the day after Thanksgiving");
  fixed(11, 25, "Christmas Day");
  cache.set(year, out);
  return out;
}

export function holidayOn(day: string) {
  const year = Number(day.slice(0, 4));
  if (!year) return "";
  return holidays(year).get(day) || holidays(year + 1).get(day) || "";
}

export function seriesDays(start: string, repeat: string, until: string, limit = 60) {
  const first = new Date(start + "T12:00");
  if (Number.isNaN(first.getTime())) return [];
  const end = until ? new Date(until + "T12:00") : new Date(first.getFullYear() + 1, first.getMonth(), first.getDate(), 12);
  const out: Date[] = [];
  if (repeat === "weekly" || repeat === "biweekly") {
    const step = repeat === "biweekly" ? 14 : 7;
    for (let d = new Date(first); d <= end && out.length < limit; d = new Date(d.getFullYear(), d.getMonth(), d.getDate() + step, 12)) out.push(d);
    return out;
  }
  const weekday = first.getDay();
  const n = repeat === "monthly_last" || Math.floor((first.getDate() - 1) / 7) + 1 > 4 ? -1 : Math.floor((first.getDate() - 1) / 7) + 1;
  for (let m = 0; out.length < limit; m += 1) {
    const d = nth(first.getFullYear(), first.getMonth() + m, weekday, n);
    if (d > end) break;
    if (d >= new Date(first.getFullYear(), first.getMonth(), first.getDate())) out.push(d);
  }
  return out;
}
