import manifest from "./sprite-manifest.json";
import type { GamePresentation, SpriteAsset, Task } from "./types";

export const spriteAssets: readonly SpriteAsset[] = manifest.sprites;
const assets = new Map(spriteAssets.map((asset) => [asset.id, asset]));
export function getSprite(id: string): SpriteAsset | undefined {
  return assets.get(id);
}
export function spriteFor(
  task: Pick<Task, "presentation">,
  role: string,
  fallback: string,
): string {
  const selected = task.presentation?.sprites?.[role];
  return selected && assets.has(selected) ? selected : fallback;
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
