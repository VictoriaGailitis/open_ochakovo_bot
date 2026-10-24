import { test } from "node:test";
import assert from "node:assert/strict";
import { moscowCalendarDate, registrationAge } from "./ageEligibility";

test("registration opens on the 18th birthday, never one day earlier", () => {
  assert.equal(registrationAge("2008-10-24", "2026-10-24"), "adult");
  assert.equal(registrationAge("2008-10-25", "2026-10-24"), "underage");
  assert.equal(registrationAge("2009-10-24", "2026-10-24"), "underage");
});

test("impossible, future and malformed dates are not classified as minors", () => {
  for (const birthday of [
    "",
    "2008-02-30",
    "2008-13-01",
    "2008-2-01",
    "2026-10-25",
    "not-a-date",
    "1900-01-01",
  ])
    assert.equal(registrationAge(birthday, "2026-10-24"), "invalid", birthday);
});

test("leap-day birthdays follow the same calendar boundary as the API", () => {
  assert.equal(registrationAge("2008-02-29", "2026-02-28"), "underage");
  assert.equal(registrationAge("2008-02-29", "2026-03-01"), "adult");
  assert.equal(registrationAge("2007-02-29", "2026-03-01"), "invalid");
});

test("Moscow midnight determines the age boundary even before midnight UTC", () => {
  const before = moscowCalendarDate(new Date("2026-10-23T20:59:59Z"));
  const after = moscowCalendarDate(new Date("2026-10-23T21:00:00Z"));
  assert.equal(before, "2026-10-23");
  assert.equal(after, "2026-10-24");
  assert.equal(registrationAge("2008-10-24", before), "underage");
  assert.equal(registrationAge("2008-10-24", after), "adult");
});
