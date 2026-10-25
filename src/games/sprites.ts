import manifest from "./sprite-manifest.json";
import type { GamePresentation, SpriteAsset, Task } from "./types";

export const spriteAssets: readonly SpriteAsset[] = manifest.sprites;
const assets = new Map(spriteAssets.map((asset) => [asset.id, asset]));
let revision = 0;
const listeners = new Set<() => void>();
let loading: Promise<void> | undefined;
let loadedAt = 0;
export const assetRevision = () => revision;
export const subscribeAssets = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
export function registerSpriteAssets(value: unknown): void {
  if (!value || typeof value !== "object")
    throw new Error("Некорректный каталог спрайтов.");
  const manifest = value as { schemaVersion?: number; sprites?: SpriteAsset[] };
  if (
    manifest.schemaVersion !== 1 ||
    !Array.isArray(manifest.sprites) ||
    manifest.sprites.length > 5000
  )
    throw new Error("Некорректный каталог спрайтов.");
  const ids = new Set<string>();
  for (const asset of manifest.sprites) {
    if (
      !asset ||
      !/^[A-Za-z0-9_-]{1,128}$/.test(asset.id) ||
      ids.has(asset.id) ||
      typeof asset.src !== "string" ||
      !/^\/(?:assets\/games-v5\/[A-Za-z0-9_.-]+|api\/game-assets\/[A-Za-z0-9_-]+\/?)$/.test(
        asset.src,
      ) ||
      ![asset.width, asset.height, asset.pixelWidth, asset.pixelHeight].every(
        (v) => Number.isFinite(v) && v > 0 && v <= 32768,
      )
    )
      throw new Error("Небезопасный или некорректный спрайт.");
    ids.add(asset.id);
  }
  for (const asset of manifest.sprites) assets.set(asset.id, { ...asset });
  revision += 1;
  listeners.forEach((listener) => listener());
}
export function loadSpriteAssets(force = false): Promise<void> {
  if (!force && !loading && Date.now() - loadedAt < 1000)
    return Promise.resolve();
  return (loading ??= fetch("/api/game-assets", { credentials: "same-origin" })
    .then(async (response) => {
      if (!response.ok)
        throw new Error("Не удалось загрузить игровые спрайты.");
      registerSpriteAssets(await response.json());
      loadedAt = Date.now();
    })
    .catch(() => {
      /* Bundled assets remain available during a transient outage. */
    })
    .finally(() => {
      loading = undefined;
    }));
}
export function getSprite(id: string): SpriteAsset | undefined {
  return assets.get(id);
}
export function spriteFor(
  task: Pick<Task, "presentation">,
  role: string,
  fallback: string,
): string {
  const selected = task.presentation?.sprites?.[role];
  return typeof selected === "string" && selected ? selected : fallback;
}

/** Validate serialized content before it reaches a renderer or a future editor preview. */
export function presentationErrors(value: unknown): string[] {
  if (!value || typeof value !== "object" || Array.isArray(value))
    return ["Оформление должно быть объектом."];
  const p = value as GamePresentation;
  if (p.schemaVersion !== 1) return ["Неизвестная версия оформления."];
  if (!p.sprites || typeof p.sprites !== "object" || Array.isArray(p.sprites))
    return ["Не заданы роли спрайтов."];
  const errors: string[] = [];
  for (const [role, id] of Object.entries(p.sprites)) {
    if (!role.trim() || typeof id !== "string" || !assets.has(id))
      errors.push(`Неизвестный спрайт для роли ${role}.`);
  }
  if (p.scene !== undefined) {
    const scene = p.scene;
    if (
      !scene ||
      !Number.isFinite(scene.width) ||
      !Number.isFinite(scene.height) ||
      scene.width <= 0 ||
      scene.height <= 0 ||
      !Array.isArray(scene.objects) ||
      scene.objects.length > 200
    )
      return [...errors, "Некорректная сцена."];
    const ids = new Set<string>();
    for (const object of scene.objects) {
      if (
        !object ||
        typeof object.id !== "string" ||
        !object.id.trim() ||
        ids.has(object.id) ||
        !assets.has(object.spriteId) ||
        ![object.x, object.y, object.width, object.height].every(
          Number.isFinite,
        ) ||
        object.width <= 0 ||
        object.height <= 0 ||
        (object.rotation !== undefined && !Number.isFinite(object.rotation)) ||
        (object.layer !== undefined &&
          (!Number.isInteger(object.layer) || Math.abs(object.layer) > 100))
      )
        errors.push("Некорректный объект сцены.");
      if (object) ids.add(object.id);
    }
  }
  return errors;
}
