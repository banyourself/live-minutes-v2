import assert from "node:assert/strict";
import test from "node:test";
import { holidayOn, holidays, isoDay, seriesDays } from "../src/holidays.ts";

test("federal holidays land on the right days, with observed weekdays", () => {
  const y2026 = holidays(2026);
  assert.equal(y2026.get("2026-01-19"), "Martin Luther King Jr. Day");
  assert.equal(y2026.get("2026-02-16"), "Presidents' Day");
  assert.equal(y2026.get("2026-05-25"), "Memorial Day");
  assert.equal(y2026.get("2026-07-03"), "Independence Day (observed)");
  assert.equal(y2026.get("2026-09-07"), "Labor Day");
  assert.equal(y2026.get("2026-10-12"), "Indigenous Peoples' Day");
  assert.equal(y2026.get("2026-11-26"), "Thanksgiving");
  assert.equal(y2026.get("2026-11-27"), "the day after Thanksgiving");
  assert.equal(holidayOn("2027-12-31"), "New Year's Day (observed)");
  assert.equal(holidayOn("2026-10-13"), "");
  assert.equal(holidayOn("not a day"), "");
});

test("series dates follow the repeat rule and stop at the end date", () => {
  const weekly = seriesDays("2026-10-07", "weekly", "2026-11-11").map(isoDay);
  assert.deepEqual(weekly, ["2026-10-07", "2026-10-14", "2026-10-21", "2026-10-28", "2026-11-04", "2026-11-11"]);
  assert.equal(seriesDays("2026-10-07", "biweekly", "2026-11-11").length, 3);
  assert.deepEqual(seriesDays("2026-10-12", "monthly", "2027-01-31").map(isoDay), ["2026-10-12", "2026-11-09", "2026-12-14", "2027-01-11"]);
  assert.deepEqual(seriesDays("2026-10-26", "monthly_last", "2026-12-31").map(isoDay), ["2026-10-26", "2026-11-30", "2026-12-28"]);
  const hits = seriesDays("2026-10-07", "weekly", "2026-12-31").map(isoDay).filter((d) => holidayOn(d));
  assert.deepEqual(hits, ["2026-11-11"]);
  assert.equal(seriesDays("2026-01-01", "weekly", "").length, 53);
});
