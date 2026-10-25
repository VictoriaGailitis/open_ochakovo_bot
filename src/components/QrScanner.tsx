import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import bridge from "@vkontakte/vk-bridge";
import type { ActivityScanResult } from "../types";
import {
  isActivityQrCode,
  isQrFrameMiss,
  isQrReaderCancellation,
  QrScanLifecycle,
  QrSubmissionGate,
  qrCameraErrorMessage,
  qrImageValidationError,
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
  | "idle"
  | "starting"
  | "camera"
  | "vk"
  | "image"
  | "submitting"
  | "result"
  | "error";

export function QrScanner({ onScan, onBack, onEvent }: QrScannerProps) {
  const [phase, setPhase] = useState<Phase>("idle"),
    [nativeUnavailable, setNativeUnavailable] = useState(false),
    [manual, setManual] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [result, setResult] = useState<ActivityScanResult | null>(null);
  const video = useRef<HTMLVideoElement>(null),
    heading = useRef<HTMLHeadingElement>(null),
    fileInput = useRef<HTMLInputElement>(null),
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
  const busy = ["starting", "vk", "image", "submitting"].includes(phase);
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
      setNotice("Сканирование остановлено. Можно попробовать другой способ.");
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
        ["starting", "camera", "image"].includes(phaseRef.current)
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
        await startCamera("Открываем камеру: встроенный сканер VK в этом клиенте недоступен.");
        return;
      }
      const response = await bridge.send("VKWebAppOpenCodeReader", {});
      if (mounted.current && attempt === operation.current)
        await acceptCode(response.code_data);
    } catch (failure) {
      if (!mounted.current || attempt !== operation.current) return;
      if (isQrReaderCancellation(failure)) {
        setPhase("idle");
        setNotice(
          "Сканирование отменено. Можно открыть сканер снова или выбрать изображение QR.",
        );
      } else {
        setNativeUnavailable(true);
        await startCamera("Сканер VK не запустился. Открываем камеру для сканирования.");
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
        "Камера недоступна в этом браузере. Для камеры нужна защищённая страница HTTPS; можно выбрать изображение QR.",
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
          showError(
            "Камера отключилась. Можно запустить её снова или выбрать изображение QR.",
          );
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
              "Не удалось прочитать изображение с камеры. Попробуй ещё раз или выбери файл QR.",
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

  async function chooseImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || gate.current.isPending || busy) return;
    const invalid = qrImageValidationError(file);
    if (invalid) {
      showError(invalid);
      return;
    }
    const session = resources.current.begin();
    operation.current++;
    retryCode.current = "";
    setError("");
    setNotice("");
    setResult(null);
    setPhase("image");
    const url = URL.createObjectURL(file);
    const releaseUrl = resources.current.own(session, () =>
      URL.revokeObjectURL(url),
    );
    let releaseImage = () => {};
    try {
      const { BrowserQRCodeReader } = await import("@zxing/browser");
      if (!mounted.current || !resources.current.isActive(session)) return;
      const image = new Image();
      image.decoding = "async";
      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(
          () => reject(new Error("Image loading timed out")),
          10000,
        );
        image.onload = () => resolve();
        image.onerror = () => reject(new Error("Image loading failed"));
        releaseImage = resources.current.own(session, () => {
          window.clearTimeout(timeout);
          image.onload = null;
          image.onerror = null;
          image.removeAttribute("src");
          reject(new DOMException("Image decoding cancelled", "AbortError"));
        });
        image.src = url;
      });
      if (!mounted.current || !resources.current.isActive(session)) return;
      if (image.naturalWidth * image.naturalHeight > 32000000) {
        showError(
          "Изображение слишком большое по размеру. Выбери уменьшенную копию или снимок только QR-кода.",
        );
        return;
      }
      const reader = new BrowserQRCodeReader();
      const decoded = await reader.decodeFromImageElement(image);
      if (mounted.current && resources.current.isActive(session))
        await acceptCode(decoded.getText());
    } catch (failure) {
      if (mounted.current && resources.current.isActive(session))
        showError(
          isQrFrameMiss(failure)
            ? "На изображении не найден читаемый QR-код. Выбери более чёткое изображение или введи код вручную."
            : "Не удалось прочитать изображение. Выбери другой файл PNG, JPEG или WebP.",
        );
    } finally {
      releaseImage();
      releaseUrl();
    }
  }
  function manualSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    void acceptCode(manual.trim());
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
                  : phase === "image"
                    ? "Читаем изображение…"
                    : phase === "submitting"
                      ? "Проверяем активность…"
                      : "Наведи камеру на QR"}
              </strong>
              <p>
                {phase === "submitting"
                  ? "Дождись ответа приложения."
                  : phase === "image"
                    ? "Камера не используется."
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
          {["starting", "camera", "vk", "image"].includes(phase) && (
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
              {inVK && !nativeUnavailable ? "Открыть сканер VK" : "Открыть камеру"}
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
          <div className="qr-file-picker">
            <input
              ref={fileInput}
              id="qr-image-file"
              type="file"
              aria-label="Файл с QR-кодом активности"
              tabIndex={-1}
              accept="image/png,image/jpeg,image/webp"
              disabled={busy}
              onChange={(event) => {
                void chooseImage(event);
              }}
            />
            <button
              type="button"
              className="qr-secondary"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
            >
              Выбрать изображение QR
            </button>
            <p className="qr-small qr-muted">PNG, JPEG или WebP · до 10 МБ</p>
          </div>
          <form className="qr-manual" onSubmit={manualSubmit}>
            <label htmlFor="qr-manual-code">Или вставь текст QR-кода</label>
            <textarea
              id="qr-manual-code"
              value={manual}
              onChange={(event) => setManual(event.target.value)}
              placeholder="ochakovo:activity:v1:…"
              maxLength={512}
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              disabled={busy}
            />
            <button
              type="submit"
              className="qr-secondary"
              disabled={busy || !manual.trim()}
            >
              Проверить код
            </button>
          </form>
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
