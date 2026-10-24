import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeReferralCode, validReferralCode } from "./types";

test("optional referral code normalizes outside spaces and case", () => {
  assert.equal(normalizeReferralCode(" oc-abcdefgh "), "OC-ABCDEFGH");
  for (const code of ["", " ", "OC-ABCDEFGH", "oc-qrstuvwx", " OC-23456789 "])
    assert.equal(validReferralCode(code), true, code);
});
test("referral format rejects ambiguous characters, foreign alphabet and malformed length", () => {
  for (const code of [
    "OC-ABCDEFGI",
    "OC-ABCDEFG0",
    "OC-ABCDEFG1",
    "OC-ABCDEFGO",
    "OC-АBCDEFGH",
    "OC-ABCD EFGH",
    "ABCDEFGH",
    "OC-ABC",
    "OC-ABCDEFGHI",
    "https://example.invalid",
  ])
    assert.equal(validReferralCode(code), false, code);
});
