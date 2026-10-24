import assert from "node:assert/strict";
import test from "node:test";
import {
  calendarDays,
  moscowDate,
  progress,
  report,
  shiftMonth,
} from "./practice/utils";
import type { Placement } from "./practice/types";

test("calendar is Monday-first, includes leap day, and crosses year boundaries", () => {
  const feb = calendarDays("2028-02");
  assert.equal(feb[0], null);
  assert.equal(feb[1], "2028-02-01");
  assert.equal(feb.filter(Boolean).length, 29);
  assert.equal(feb.length % 7, 0);
  assert.equal(shiftMonth("2026-12", 1), "2027-01");
  assert.equal(shiftMonth("2026-01", -1), "2025-12");
  assert.equal(moscowDate("2026-10-24T22:30:00Z"), "2026-10-25");
});
test("period progress clamps outside its dates and report omits private answers", () => {
  const p = {
    title: "Практика",
    studentName: "Анна",
    start_date: "2026-10-10",
    end_date: "2026-10-20",
    mentor: null,
    goals: [],
    feedback: [],
    checkins: [{ answers: { comment: "Личное" } }],
  } as unknown as Placement;
  assert.equal(progress(p, "2026-10-01"), 0);
  assert.equal(progress(p, "2026-10-15"), 50);
  assert.equal(progress(p, "2026-11-01"), 100);
  assert.ok(!report(p).includes("Личное"));
  assert.ok(report(p).includes("Анна"));
});
