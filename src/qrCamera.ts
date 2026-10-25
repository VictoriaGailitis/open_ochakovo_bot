import { QrScanLifecycle } from "./qrScanner";

/** WebViews can resolve play() before video dimensions / the first frame exist. */
export function prepareQrVideo(
  video: HTMLVideoElement,
  stream: MediaStream,
  lifecycle: QrScanLifecycle,
  session: number,
  timeoutMs = 10000,
): Promise<void> {
  return new Promise((resolve, reject) => {
    let release = () => {};
    const ready = () => {
      if (
        !video.paused &&
        video.readyState >= 2 &&
        video.videoWidth > 0 &&
        video.videoHeight > 0
      ) {
        resolve();
        release();
      }
    };
    const fail = (error: unknown) => {
      reject(error);
      release();
    };
    const timeout = setTimeout(
      () => fail(new Error("Camera produced no video frames")),
      timeoutMs,
    );
    // Some VK WebViews omit media events, so also check the actual video state.
    const poll = setInterval(ready, 100);
    const events = ["loadeddata", "playing", "resize"];
    for (const event of events) video.addEventListener(event, ready);
    release = lifecycle.own(session, () => {
      clearTimeout(timeout);
      clearInterval(poll);
      for (const event of events) video.removeEventListener(event, ready);
      reject(new DOMException("Camera cancelled", "AbortError"));
    });
    if (!lifecycle.isActive(session)) return;
    try {
      video.muted = true;
      video.playsInline = true;
      video.srcObject = stream;
      void video.play().then(ready, fail);
    } catch (error) {
      fail(error);
    }
  });
}
