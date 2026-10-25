import { useEffect, useSyncExternalStore } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { Task } from "./types";
import {
  getSprite,
  presentationErrors,
  loadSpriteAssets,
  subscribeAssets,
  assetRevision,
} from "./sprites";
function useAssets(spriteId?: string) {
  useSyncExternalStore(subscribeAssets, assetRevision, assetRevision);
  useEffect(() => {
    void loadSpriteAssets(Boolean(spriteId && !getSprite(spriteId)));
  }, [spriteId]);
}
import "./sprites.css";
export { spriteFor } from "./sprites";

export function GameSprite({
  spriteId,
  className = "",
  style,
  alt = "",
}: {
  spriteId: string;
  className?: string;
  style?: CSSProperties;
  alt?: string;
}) {
  useAssets(spriteId);
  const asset = getSprite(spriteId);
  if (!asset) return null;
  return (
    <span
      className={`game-sprite ${className}`}
      style={style}
      data-sprite={asset.id}
    >
      <img
        src={asset.src}
        width={asset.width}
        height={asset.height}
        alt={alt}
        draggable={false}
      />
    </span>
  );
}

export function GameScene({
  task,
  className = "",
  children,
  label,
}: {
  task: Pick<Task, "presentation">;
  className?: string;
  children?: ReactNode;
  label?: string;
}) {
  useAssets();
  const scene =
    task.presentation && presentationErrors(task.presentation).length === 0
      ? task.presentation.scene
      : undefined;
  return (
    <div className={`game-scene ${className}`} aria-label={label}>
      {scene && (
        <div className="game-scene-objects" aria-hidden="true">
          {scene.objects.map((object) => (
            <GameSprite
              key={object.id}
              spriteId={object.spriteId}
              style={{
                position: "absolute",
                left: `${(object.x / scene.width) * 100}%`,
                top: `${(object.y / scene.height) * 100}%`,
                width: `${(object.width / scene.width) * 100}%`,
                height: `${(object.height / scene.height) * 100}%`,
                transform: `rotate(${object.rotation ?? 0}deg)`,
                zIndex: object.layer ?? 0,
              }}
            />
          ))}
        </div>
      )}
      {children}
    </div>
  );
}
