import { test } from "node:test";
import assert from "node:assert/strict";
import {
  ACTIVITY_QR_PREFIX,
  MAX_QR_IMAGE_BYTES,
  QrScanLifecycle,
  QrSubmissionGate,
  isActivityQrCode,
  isQrFrameMiss,
  isQrReaderCancellation,
  qrCameraErrorMessage,
  qrImageValidationError,
  qrScanErrorMessage,
} from "./qrScanner";
const code = ACTIVITY_QR_PREFIX + "A".repeat(41) + "_-";

test("activity scanner accepts only the complete versioned opaque-token format", () => {
  assert.equal(isActivityQrCode(code), true);
  for (const foreign of [
    null,
    42,
    "",
    "https://example.org/" + code,
    "javascript:alert(1)",
    "ochakovo:activity:v0:" + "A".repeat(43),
    ACTIVITY_QR_PREFIX + "A".repeat(42),
    ACTIVITY_QR_PREFIX + "A".repeat(44),
    ACTIVITY_QR_PREFIX + "A".repeat(42) + "/",
    ACTIVITY_QR_PREFIX + "A".repeat(42) + "Я",
    code + "\n",
    " " + code,
  ])
    assert.equal(
      isActivityQrCode(foreign),
      false,
      String(foreign).slice(0, 24),
    );
});

test("selected QR image validates MIME, nonempty size and the 10 MB limit", () => {
  for (const type of ["image/png", "image/jpeg", "image/webp"])
    assert.equal(
      qrImageValidationError({ type, size: MAX_QR_IMAGE_BYTES }),
      null,
    );
  assert.match(
    qrImageValidationError({ type: "image/svg+xml", size: 100 })!,
    /PNG/,
  );
  assert.match(
    qrImageValidationError({
      type: "image/png",
      size: MAX_QR_IMAGE_BYTES + 1,
    })!,
    /10 МБ/,
  );
  assert.match(
    qrImageValidationError({ type: "image/jpeg", size: 0 })!,
    /пустое/,
  );
  assert.match(
    qrImageValidationError({ type: "image/webp", size: NaN })!,
    /пустое/,
  );
});

test("scanner stop releases controls, tracks and object URLs once, in reverse acquisition order", () => {
  const scanner = new QrScanLifecycle(),
    session = scanner.begin(),
    calls: string[] = [];
  scanner.own(session, () => {
    calls.push("tracks");
  });
  const releaseUrl = scanner.own(session, () => {
    calls.push("blob URL");
  });
  scanner.own(session, () => {
    calls.push("decoder");
  });
  scanner.stop();
  scanner.stop();
  releaseUrl();
  assert.deepEqual(calls, ["decoder", "blob URL", "tracks"]);
  assert.equal(scanner.isActive(session), false);
});

test("late camera or decoder acquisition is stopped immediately without affecting a new session", () => {
  const scanner = new QrScanLifecycle(),
    old = scanner.begin(),
    active = scanner.begin();
  let lateStopped = 0,
    newStopped = 0;
  scanner.own(active, () => {
    newStopped++;
  });
  scanner.own(old, () => {
    lateStopped++;
  });
  assert.equal(lateStopped, 1);
  assert.equal(newStopped, 0);
  assert.equal(scanner.isActive(active), true);
  scanner.stop();
  assert.equal(newStopped, 1);
});

test("a cleanup failure cannot prevent releasing the remaining scanner resources", async () => {
  const scanner = new QrScanLifecycle(),
    session = scanner.begin();
  let stopped = false;
  scanner.own(session, () => {
    stopped = true;
  });
  scanner.own(session, () =>
    Promise.reject(new Error("decoder already closed")),
  );
  scanner.own(session, () => {
    throw new Error("already revoked");
  });
  scanner.stop();
  await Promise.resolve();
  assert.equal(stopped, true);
});

test("repeated frames submit one pending request, then permit an explicit retry", async () => {
  const gate = new QrSubmissionGate();
  let calls = 0,
    resolve = () => {};
  const pending = new Promise<void>((done) => {
    resolve = done;
  });
  const submit = async () => {
    if (!gate.acquire()) return false;
    calls++;
    try {
      await pending;
      return true;
    } finally {
      gate.release();
    }
  };
  const first = submit();
  assert.equal(gate.isPending, true);
  assert.equal(await submit(), false);
  assert.equal(calls, 1);
  resolve();
  assert.equal(await first, true);
  assert.equal(gate.isPending, false);
  assert.equal(await submit(), true);
  assert.equal(calls, 2);
});

test("ordinary missing QR frames continue scanning, while unexpected decoder errors do not", () => {
  assert.equal(isQrFrameMiss({ getKind: () => "NotFoundException" }), true);
  assert.equal(isQrFrameMiss({ name: "ChecksumException" }), true);
  assert.equal(isQrFrameMiss({ name: "FormatException" }), true);
  assert.equal(isQrFrameMiss(new Error("Canvas unavailable")), false);
});

test("native cancellation is recognized without guessing VK numeric error codes", () => {
  assert.equal(
    isQrReaderCancellation({ error_data: { error_reason: "User cancelled" } }),
    true,
  );
  assert.equal(
    isQrReaderCancellation({ error_data: { error_reason: "User denied" } }),
    true,
  );
  assert.equal(isQrReaderCancellation({ name: "AbortError" }), true);
  assert.equal(
    isQrReaderCancellation({
      error_data: { error_code: 4, error_reason: "Client unavailable" },
    }),
    false,
  );
});

test("camera errors offer an explicit fallback and never include QR secrets in error text", () => {
  assert.match(
    qrCameraErrorMessage({ name: "NotAllowedError" }),
    /не разрешён/,
  );
  assert.match(qrCameraErrorMessage({ name: "NotFoundError" }), /не найдена/);
  const message = qrScanErrorMessage(
    new Error("Unknown " + code + "; retry " + code),
    code,
  );
  assert.equal(message.includes(code), false);
  assert.equal(message.includes("A".repeat(41)), false);
  assert.equal(
    qrScanErrorMessage(new Error("Unknown " + code)).includes("A".repeat(41)),
    false,
  );
});
