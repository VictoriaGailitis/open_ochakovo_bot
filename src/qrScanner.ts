export const ACTIVITY_QR_PREFIX = "ochakovo:activity:v1:";
export const MAX_QR_IMAGE_BYTES = 10 * 1024 * 1024;
const activityCode = /^ochakovo:activity:v1:[A-Za-z0-9_-]{43}$/;
const imageTypes = new Set(["image/png", "image/jpeg", "image/webp"]);

export function isActivityQrCode(value: unknown): value is string {
  return typeof value === "string" && activityCode.test(value);
}

export function qrImageValidationError(file: {
  type: string;
  size: number;
}): string | null {
  if (!imageTypes.has(file.type))
    return "Выбери изображение PNG, JPEG или WebP.";
  if (!Number.isFinite(file.size) || file.size <= 0)
    return "Изображение пустое. Выбери другой файл.";
  if (file.size > MAX_QR_IMAGE_BYTES)
    return "Изображение больше 10 МБ. Выбери файл поменьше.";
  return null;
}

type Releaser = () => void | Promise<void>;
/** Owns only this scanner's resources; late asynchronous results are released immediately. */
export class QrScanLifecycle {
  private generation = 0;
  private resources = new Set<() => void>();
  begin(): number {
    this.stop();
    return this.generation;
  }
  isActive(generation: number): boolean {
    return generation === this.generation;
  }
  own(generation: number, release: Releaser): () => void {
    let released = false;
    const once = () => {
      if (released) return;
      released = true;
      this.resources.delete(once);
      try {
        const pending = release();
        if (pending) void pending.catch(() => undefined);
      } catch {
        /* Continue releasing other owned resources. */
      }
    };
    if (this.isActive(generation)) this.resources.add(once);
    else once();
    return once;
  }
  stop(): void {
    this.generation++;
    for (const release of [...this.resources].reverse()) release();
  }
}

/** Synchronous lock: React state alone cannot reject duplicate decoder frames. */
export class QrSubmissionGate {
  private pending = false;
  acquire(): boolean {
    if (this.pending) return false;
    this.pending = true;
    return true;
  }
  release(): void {
    this.pending = false;
  }
  get isPending(): boolean {
    return this.pending;
  }
}

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object"
    ? (value as Record<string, unknown>)
    : {};
}
export function isQrFrameMiss(error: unknown): boolean {
  const value = object(error);
  let kind = value.name;
  if (typeof value.getKind === "function") {
    try {
      kind = value.getKind();
    } catch {
      return false;
    }
  }
  return ["NotFoundException", "ChecksumException", "FormatException"].includes(
    String(kind),
  );
}
export function isQrReaderCancellation(error: unknown): boolean {
  const value = object(error),
    data = object(value.error_data);
  const message = [value.name, value.message, data.error_reason, data.message]
    .filter((v) => typeof v === "string")
    .join(" ");
  return /abort|cancel|отмен|closed by user|user denied|user refused/i.test(
    message,
  );
}
export function qrCameraErrorMessage(error: unknown): string {
  const name = object(error).name;
  if (name === "NotAllowedError" || name === "PermissionDeniedError")
    return "Доступ к камере не разрешён. Можно выбрать изображение QR или ввести код вручную.";
  if (name === "NotFoundError" || name === "DevicesNotFoundError")
    return "Камера не найдена. Выбери изображение QR или введи код вручную.";
  if (name === "NotReadableError" || name === "TrackStartError")
    return "Камера занята другим приложением. Закрой его и попробуй ещё раз либо выбери изображение QR.";
  if (name === "SecurityError")
    return "Браузер не разрешает камеру на этой странице. Открой приложение по HTTPS или выбери изображение QR.";
  return "Не удалось запустить камеру. Попробуй ещё раз, выбери изображение QR или введи код вручную.";
}
export function qrScanErrorMessage(error: unknown, rawCode = ""): string {
  const value = object(error);
  let message =
    typeof value.message === "string" && value.message
      ? value.message
      : "Не удалось проверить активность. Код сохранён для повторной попытки.";
  if (rawCode) message = message.split(rawCode).join("[код активности]");
  return message
    .replace(/ochakovo:activity:v1:[^\s"'<>]+/g, "[код активности]")
    .slice(0, 400);
}
