import { test } from "node:test";
import assert from "node:assert/strict";
import { prepareQrVideo } from "./qrCamera";
import { QrScanLifecycle } from "./qrScanner";

class Preview extends EventTarget {
  paused = false;
  readyState = 0;
  videoWidth = 0;
  videoHeight = 0;
  muted = false;
  playsInline = false;
  srcObject: unknown = null;
  async play() {}
  frame() {
    this.readyState = 2;
    this.videoWidth = 1280;
    this.videoHeight = 720;
    this.dispatchEvent(new Event("playing"));
  }
}
function prepare(preview: Preview, lifecycle: QrScanLifecycle, session: number, timeout = 500) {
  return prepareQrVideo(preview as unknown as HTMLVideoElement, {} as MediaStream, lifecycle, session, timeout);
}

test("camera waits for actual frame dimensions even after play resolves", async () => {
  const lifecycle = new QrScanLifecycle(), session = lifecycle.begin(), preview = new Preview();
  let ready = false;
  const pending = prepare(preview, lifecycle, session).then(() => { ready = true; });
  await Promise.resolve();
  assert.equal(ready, false);
  assert.equal(preview.muted, true);
  assert.equal(preview.playsInline, true);
  preview.frame();
  await pending;
  assert.equal(ready, true);
  assert.equal(lifecycle.isActive(session), true);
  lifecycle.stop();
});

test("camera can start when play stays pending but a real video frame arrives", async () => {
  const lifecycle = new QrScanLifecycle(), session = lifecycle.begin(), preview = new Preview();
  preview.play = () => new Promise(() => {});
  const pending = prepare(preview, lifecycle, session);
  preview.frame();
  await pending;
  lifecycle.stop();
});

test("a WebView that omits media events is detected from its real video state", async () => {
  const lifecycle = new QrScanLifecycle(), session = lifecycle.begin(), preview = new Preview();
  const pending = prepare(preview, lifecycle, session);
  await Promise.resolve();
  preview.readyState = 2;
  preview.videoWidth = 720;
  preview.videoHeight = 1280;
  await pending;
  lifecycle.stop();
});

test("cancelling during camera startup rejects the wait and ignores late frames", async () => {
  const lifecycle = new QrScanLifecycle(), session = lifecycle.begin(), preview = new Preview();
  const pending = prepare(preview, lifecycle, session);
  lifecycle.stop();
  await assert.rejects(pending, { name: "AbortError" });
  preview.frame();
  assert.equal(lifecycle.isActive(session), false);
});

test("camera startup failures and missing frames fail instead of hanging", async () => {
  const lifecycle = new QrScanLifecycle(), preview = new Preview();
  preview.play = async () => { throw new DOMException("Blocked", "NotAllowedError"); };
  await assert.rejects(prepare(preview, lifecycle, lifecycle.begin()), { name: "NotAllowedError" });
  preview.play = async () => {};
  await assert.rejects(prepare(preview, lifecycle, lifecycle.begin(), 10), /no video frames/);
  lifecycle.stop();
});
