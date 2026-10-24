import { useEffect, useRef, useState } from "react";
import type { GameDefinition, Task } from "./types";
import type { Progress } from "../types";
import { GameSprite } from "./GameSprite";
import "./catalog.css";

export function GameCatalog({
  games,
  tasks,
  progress,
  onSelect,
}: {
  games?: GameDefinition[];
  tasks: Task[];
  progress: Progress[];
  onSelect: (id: string) => void;
}) {
  const [selected, setSelected] = useState<GameDefinition | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const definitions =
    games ??
    [...new Set(tasks.map((task) => task.game))].map((id) => ({
      id,
      title: tasks.find((task) => task.game === id)!.title,
      description: tasks.find((task) => task.game === id)!.description,
      previewSpriteId: tasks.find((task) => task.game === id)?.presentation
        ?.sprites.preview,
    }));
  const playable = definitions.filter(
    (game) =>
      game.id !== "history" && tasks.some((task) => task.game === game.id),
  );
  const history = definitions.find((game) => game.id === "history");
  useEffect(() => {
    if (selected) {
      if (!dialog.current?.open) dialog.current?.showModal();
    } else dialog.current?.close();
  }, [selected]);
  function open(game: GameDefinition) {
    const levels = tasks.filter((task) => task.game === game.id);
    if (levels.length === 1) onSelect(levels[0].id);
    else setSelected(game);
  }
  return (
    <section className="game-catalog" aria-label="Игровая зона">
      <h1>Игровая зона</h1>
      <p className="catalog-eyebrow">
        {playable.length} ИГР · ВЫБЕРИ СВОЁ ДЕЛО
      </p>
      {playable.map((game, index) => (
        <button
          key={game.id}
          className={`catalog-game ${index === 0 ? "catalog-game-featured" : ""}`}
          onClick={() => open(game)}
        >
          <span className="catalog-game-icon">
            <GameSprite spriteId={game.previewSpriteId ?? ""} />
          </span>
          <span className="catalog-game-copy">
            <strong>{game.title}</strong>
            <span>{game.description}</span>
          </span>
        </button>
      ))}
      {history && (
        <button className="catalog-history" onClick={() => open(history)}>
          ОТКРОЙ ИСТОРИЮ ОЧАКОВО →
        </button>
      )}
      <dialog
        ref={dialog}
        aria-labelledby="catalog-level-title"
        className="catalog-level-dialog"
        onClose={() => setSelected(null)}
        onCancel={() => setSelected(null)}
      >
        {selected && (
          <>
            <div className="catalog-level-head">
              <h2 id="catalog-level-title">{selected.title}</h2>
              <button
                aria-label="Закрыть выбор уровня"
                onClick={() => setSelected(null)}
              >
                ×
              </button>
            </div>
            <p>Выбери уровень. Начатый прогресс сохранён.</p>
            <div className="catalog-levels">
              {tasks
                .filter((task) => task.game === selected.id)
                .sort((a, b) => a.level - b.level)
                .map((task) => {
                  const saved = progress.find((item) => item.task === task.id);
                  return (
                    <button
                      key={task.id}
                      onClick={() => {
                        setSelected(null);
                        onSelect(task.id);
                      }}
                    >
                      <strong>
                        Уровень {String(task.level).padStart(2, "0")}
                      </strong>
                      <span>
                        {saved?.completed
                          ? "Пройден · тренироваться ещё"
                          : saved
                            ? "Продолжить"
                            : `${task.duration} · +${task.points} баллов`}
                      </span>
                    </button>
                  );
                })}
            </div>
          </>
        )}
      </dialog>
    </section>
  );
}
