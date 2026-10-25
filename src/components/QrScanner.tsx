import { useEffect, useRef, useState } from "react";
import bridge from "@vkontakte/vk-bridge";
import type { ActivityScanResult } from "../types";
import {
  isActivityQrCode,
  isQrFrameMiss,
  isQrReaderCancellation,
  QrScanLifecycle,
  QrSubmissionGate,
  qrCameraErrorMessage,
  qrScanErrorMessage,
  supportsNativeQrReader,
} from "../qrScanner";
import { prepareQrVideo } from "../qrCamera";
import "./qr-scanner.css";

export interface QrScannerProps {
  onScan: (code: string) => Promise<ActivityScanResult>;
  onBack: () => void;
  onEvent: (id: string) => void;
}
type Phase =
  "idle" | "starting" | "camera" | "vk" | "submitting" | "result" | "error";

export function QrScanner({ onScan, onBack, onEvent }: QrScannerProps) {
  const [phase, setPhase] = useState<Phase>("idle"),
    [nativeUnavailable, setNativeUnavailable] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [result, setResult] = useState<ActivityScanResult | null>(null);
  const video = useRef<HTMLVideoElement>(null),
    heading = useRef<HTMLHeadingElement>(null),
    mounted = useRef(true),
    operation = useRef(0),
    phaseRef = useRef<Phase>("idle"),
    resources = useRef(new QrScanLifecycle()),
    gate = useRef(new QrSubmissionGate()),
    retryCode = useRef(""),
    scanRef = useRef(onScan);
  phaseRef.current = phase;
  scanRef.current = onScan;
  const inVK =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).has("vk_user_id");
  const busy = ["starting", "vk", "submitting"].includes(phase);
  const cameraVisible = phase === "starting" || phase === "camera";

  useEffect(() => {
    if (phase === "result") {
      window.scrollTo(0, 0);
      heading.current?.focus({ preventScroll: true });
    }
  }, [phase]);

  function stopCapture() {
    resources.current.stop();
  }
  function showError(message: string) {
    stopCapture();
    if (mounted.current) {
      setError(message);
      setNotice("");
      setPhase("error");
    }
  }
  function cancelCapture() {
    operation.current++;
    stopCapture();
    if (mounted.current) {
      setPhase("idle");
      setNotice("Сканирование остановлено. Можно запустить камеру снова.");
    }
  }
  function leave() {
    operation.current++;
    stopCapture();
    onBack();
  }
  function scanAnother() {
    operation.current++;
    stopCapture();
    retryCode.current = "";
    setResult(null);
    setError("");
    setNotice("");
    setPhase("idle");
  }

  useEffect(() => {
    mounted.current = true;
    const suspend = () => {
      stopCapture();
      if (
        mounted.current &&
        ["starting", "camera"].includes(phaseRef.current)
      ) {
        setPhase("idle");
        setNotice(
          "Камера остановлена. Чтобы продолжить, нажми «Открыть камеру».",
        );
      }
    };
    const visibility = () => {
      if (document.hidden) suspend();
    };
    const hide = () => suspend();
    // Opening VK's native reader can hide the WebView; its promised result stays valid.
    const vkVisibility = (event: { detail?: { type?: string } }) => {
      if (event.detail?.type === "VKWebAppViewHide") suspend();
    };
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", hide);
    bridge.subscribe(vkVisibility);
    return () => {
      mounted.current = false;
      operation.current++;
      stopCapture();
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("pagehide", hide);
      bridge.unsubscribe(vkVisibility);
    };
  }, []);

  async function acceptCode(code: string) {
    if (!mounted.current || gate.current.isPending) return;
    if (!isActivityQrCode(code)) {
      retryCode.current = "";
      showError(
        "Этот QR-код не относится к активности приложения. Попроси код активности у организатора.",
      );
      return;
    }
    if (!gate.current.acquire()) return;
    const attempt = ++operation.current;
    stopCapture();
    retryCode.current = code;
    setResult(null);
    setError("");
    setNotice("");
    setPhase("submitting");
    try {
      const response = await scanRef.current(code);
      if (mounted.current && attempt === operation.current) {
        stopCapture();
        setResult(response);
        setPhase("result");
      }
    } catch (failure) {
      if (mounted.current && attempt === operation.current)
        showError(
          typeof navigator !== "undefined" && navigator.onLine === false
            ? "Нет подключения к интернету. Код сохранён: повтори проверку, когда появится сеть."
            : qrScanErrorMessage(failure, code),
        );
    } finally {
      gate.current.release();
    }
  }

  async function openNative() {
    if (gate.current.isPending || busy) return;
    stopCapture();
    retryCode.current = "";
    const attempt = ++operation.current;
    setError("");
    setNotice("");
    setResult(null);
    setPhase("vk");
    try {
      const supported = await supportsNativeQrReader(bridge);
      if (!mounted.current || attempt !== operation.current) return;
      if (!supported) {
        setNativeUnavailable(true);
        await startCamera(
          "Открываем камеру: встроенный сканер VK в этом клиенте недоступен.",
        );
        return;
      }
      const response = await bridge.send("VKWebAppOpenCodeReader", {});
      if (mounted.current && attempt === operation.current)
        await acceptCode(response.code_data);
    } catch (failure) {
      if (!mounted.current || attempt !== operation.current) return;
      if (isQrReaderCancellation(failure)) {
        setPhase("idle");
        setNotice("Сканирование отменено. Можно открыть сканер снова.");
      } else {
        setNativeUnavailable(true);
        await startCamera(
          "Сканер VK не запустился. Открываем камеру для сканирования.",
        );
      }
    }
  }

  async function openCamera() {
    if (gate.current.isPending || busy) return;
    await startCamera();
  }

  async function startCamera(message = "") {
    const session = resources.current.begin();
    operation.current++;
    retryCode.current = "";
    setError("");
    setNotice(message);
    setResult(null);
    setPhase("starting");
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      showError(
        "Камера недоступна в этом браузере. Открой приложение по HTTPS в клиенте с поддержкой камеры.",
      );
      return;
    }
    try {
      const { BrowserQRCodeReader } = await import("@zxing/browser");
      if (!mounted.current || !resources.current.isActive(session)) return;
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
      const preview = video.current;
      const ended = () => {
        if (resources.current.isActive(session))
          showError("Камера отключилась. Попробуй запустить её снова.");
      };
      for (const track of stream.getTracks())
        track.addEventListener("ended", ended);
      resources.current.own(session, () => {
        for (const track of stream.getTracks()) {
          track.removeEventListener("ended", ended);
          track.stop();
        }
        if (preview && preview.srcObject === stream) {
          preview.pause();
          preview.srcObject = null;
          preview.removeAttribute("src");
        }
      });
      if (!mounted.current || !resources.current.isActive(session)) return;
      if (!preview) throw new Error("Preview unavailable");
      await prepareQrVideo(preview, stream, resources.current, session);
      if (!mounted.current || !resources.current.isActive(session)) return;
      setPhase("camera");
      const reader = new BrowserQRCodeReader(undefined, {
        delayBetweenScanAttempts: 250,
        delayBetweenScanSuccess: 500,
      });
      // The preview is already playing and has real frame dimensions. Avoid
      // decodeFromStream's second playback wait, which can hang in WebViews.
      const controls = reader.scan(
        preview,
        (decoded, failure, scanControls) => {
          if (!mounted.current || !resources.current.isActive(session)) {
            scanControls.stop();
            return;
          }
          if (decoded) {
            scanControls.stop();
            void acceptCode(decoded.getText());
            return;
          }
          if (failure && !isQrFrameMiss(failure)) {
            scanControls.stop();
            showError(
              "Не удалось прочитать QR с камеры. Запусти сканирование снова и помести QR в центр кадра.",
            );
          }
        },
      );
      resources.current.own(session, () => controls.stop());
    } catch (failure) {
      if (mounted.current && resources.current.isActive(session))
        showError(qrCameraErrorMessage(failure));
    }
  }

  return (
    <section
      className="qr-scanner"
      aria-labelledby="qr-scanner-title"
      aria-busy={busy}
    >
      <button type="button" className="qr-back" onClick={leave}>
        ← События
      </button>
      <p className="qr-eyebrow">ОТКРЫВАЕМ НОВЫЙ ОПЫТ</p>
      <h1 id="qr-scanner-title" ref={heading} tabIndex={-1}>
        QR активности
      </h1>
      {result ? (
        <div className="qr-result" role="status">
          <span className="qr-result-mark" aria-hidden="true">
            ✓
          </span>
          <p className="qr-eyebrow">
            {result.alreadyCompleted ? "УЖЕ ОТМЕЧЕНО" : "АКТИВНОСТЬ ЗАЧТЕНА"}
          </p>
          <h2>{result.activity.title}</h2>
          <p className="qr-muted">{result.event.title}</p>
          <p>{result.activity.description}</p>
          <strong className="qr-points">
            {result.alreadyCompleted
              ? "Без повторного начисления"
              : `+${result.pointsAwarded} баллов`}
          </strong>
          <p>
            Баланс: <strong>{result.balance} баллов</strong>
          </p>
          <button
            type="button"
            className="qr-primary"
            onClick={() => {
              stopCapture();
              onEvent(result.event.id);
            }}
          >
            К мероприятию →
          </button>
          <button type="button" className="qr-secondary" onClick={scanAnother}>
            Сканировать другой QR
          </button>
          <button type="button" className="qr-link" onClick={leave}>
            Вернуться к событиям
          </button>
        </div>
      ) : (
        <>
          <p className="qr-description">
            Отсканируй QR у организатора мероприятия. Приложение проверит
            активность и покажет результат.
          </p>
          <div className={`qr-camera ${cameraVisible ? "is-active" : ""}`}>
            <video
              ref={video}
              autoPlay
              muted
              playsInline
              aria-label="Изображение с камеры для QR"
              hidden={!cameraVisible}
            />
            <div className="qr-camera-placeholder" hidden={cameraVisible}>
              <span className="qr-viewfinder" aria-hidden="true">
                ⌗
              </span>
              <strong>
                {phase === "vk"
                  ? "Открыт сканер VK"
                  : phase === "submitting"
                    ? "Проверяем активность…"
                    : "Наведи камеру на QR"}
              </strong>
              <p>
                {phase === "submitting"
                  ? "Дождись ответа приложения."
                  : "Камера включается только по твоему нажатию."}
              </p>
            </div>
            {cameraVisible && (
              <div className="qr-camera-label" role="status">
                {phase === "starting"
                  ? "Запускаем камеру…"
                  : "Помести QR в центр кадра"}
              </div>
            )}
          </div>
          {phase === "submitting" && (
            <p className="qr-status" role="status">
              Проверяем код. Повторно сканировать его сейчас не нужно.
            </p>
          )}
          {error && (
            <p className="qr-error" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="qr-status" role="status">
              {notice}
            </p>
          )}
          {retryCode.current && phase === "error" && (
            <button
              type="button"
              className="qr-primary"
              onClick={() => {
                void acceptCode(retryCode.current);
              }}
            >
              Повторить проверку
            </button>
          )}
          {["starting", "camera", "vk"].includes(phase) && (
            <button
              type="button"
              className="qr-secondary"
              onClick={cancelCapture}
            >
              Остановить сканирование
            </button>
          )}
          {!cameraVisible && (
            <button
              type="button"
              className="qr-primary"
              disabled={busy}
              onClick={() => {
                void (inVK && !nativeUnavailable ? openNative() : openCamera());
              }}
            >
              {inVK && !nativeUnavailable
                ? "Открыть сканер VK"
                : "Открыть камеру"}
            </button>
          )}
          {inVK && !nativeUnavailable && !cameraVisible && (
            <button
              type="button"
              className="qr-link"
              disabled={busy}
              onClick={() => {
                void openCamera();
              }}
            >
              Использовать камеру браузера →
            </button>
          )}
          <p className="qr-small qr-muted">
            Засчитываются только QR активностей этого приложения. Баллы за одну
            активность начисляются один раз.
          </p>
        </>
      )}
    </section>
  );
}
export default QrScanner;
