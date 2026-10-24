import { test } from "node:test";
import assert from "node:assert/strict";
import { staffDestination, staffHome } from "./staffRoutes";

test("employees land in the community without being routed through practice", () => {
  assert.equal(staffHome("employee"), "employee");
  assert.equal(staffDestination("employee", "practice"), "employee");
  assert.equal(staffDestination("employee", "mentor"), "employee");
  assert.equal(staffDestination("employee", "community"), "community");
});

test("practice accounts retain their own workspace and can enter the shared community", () => {
  assert.equal(staffDestination("intern", "mentor"), "practice");
  assert.equal(staffDestination("mentor", "practice"), "mentor");
  for (const role of ["intern", "mentor"] as const) {
    assert.equal(staffDestination(role, "community"), "community");
    assert.equal(staffDestination(role, "employee"), "employee");
  }
});
