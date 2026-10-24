import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ApiClient, MediaLoader } from "../api";
import type {
  Material,
  MaterialBlock,
  MaterialCategory,
  MaterialResult,
  MaterialSummary,
} from "./types";
import "./learning.css";

export interface LearningProps {
  client: ApiClient;
  onEarned?: () => void | Promise<void>;
  initialMaterialId?: string;
  loadMedia?: MediaLoader;
}
const categories: { id: "all" | MaterialCategory; label: string }[] = [
  { id: "all", label: "Все" },
  { id: "company", label: "О компании" },
  { id: "video", label: "Видео" },
  { id: "practice", label: "Практика" },
  { id: "stories", label: "Истории сотрудников" },
];
const categoryLabel = (category: string) =>
  categories.find((item) => item.id === category)?.label ?? "Материал";
const message = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Не удалось загрузить материал. Попробуй ещё раз.";

export function Learning({
  client,
  onEarned,
  initialMaterialId,
  loadMedia,
}: LearningProps) {
  const [materials, setMaterials] = useState<MaterialSummary[] | null>(null),
    [listError, setListError] = useState("");
  const [category, setCategory] = useState<"all" | MaterialCategory>("all"),
    [materialId, setMaterialId] = useState(initialMaterialId ?? "");
  const [material, setMaterial] = useState<Material | null>(null),
    [readerError, setReaderError] = useState(""),
    [attempt, setAttempt] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({}),
    [result, setResult] = useState<MaterialResult | null>(null),
    [submitting, setSubmitting] = useState(false),
    [notice, setNotice] = useState("");
  const pending = useRef(false),
    mounted = useRef(true),
    request = useRef(0),
    heading = useRef<HTMLHeadingElement>(null),
    resultHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      request.current++;
    };
  }, []);
  useEffect(() => {
    setMaterialId(initialMaterialId ?? "");
  }, [initialMaterialId]);
  useEffect(() => {
    let live = true;
    setMaterials(null);
    setListError("");
    void client<{ materials: MaterialSummary[] }>("/materials")
      .then((value) => {
        if (live) setMaterials(value.materials);
      })
      .catch((error) => {
        if (live) setListError(message(error));
      });
    return () => {
      live = false;
    };
  }, [client, attempt]);
  useEffect(() => {
    let live = true;
    request.current++;
    setMaterial(null);
    setReaderError("");
    setAnswers({});
    setResult(null);
    setNotice("");
    setSubmitting(false);
    pending.current = false;
    if (materialId)
      void client<{ material: Material }>(
        "/materials/" + encodeURIComponent(materialId),
      )
        .then((value) => {
          if (live) setMaterial(value.material);
        })
        .catch((error) => {
          if (live) setReaderError(message(error));
        });
    return () => {
      live = false;
    };
  }, [client, materialId, attempt]);
  useEffect(() => {
    if (material) {
      heading.current?.scrollIntoView({ block: "start" });
      heading.current?.focus({ preventScroll: true });
    }
  }, [material?.id]);
  useEffect(() => {
    if (result) {
      resultHeading.current?.scrollIntoView({ block: "center" });
      resultHeading.current?.focus({ preventScroll: true });
    }
  }, [result]);
  async function complete(event: FormEvent) {
    event.preventDefault();
    if (!material?.quiz || pending.current) return;
    pending.current = true;
    setSubmitting(true);
    setReaderError("");
    setNotice("");
    const currentRequest = request.current,
      id = material.id;
    try {
      const response = await client<MaterialResult>(
        `/materials/${encodeURIComponent(id)}/complete`,
        "POST",
        { answers, version: material.version },
      );
      if (!mounted.current || request.current !== currentRequest) return;
      setResult(response);
      if (response.correct && response.completion) {
        setMaterial((current) =>
          current?.id === id
            ? { ...current, completion: response.completion! }
            : current,
        );
        setMaterials(
          (current) =>
            current?.map((item) =>
              item.id === id
                ? { ...item, completion: response.completion! }
                : item,
            ) ?? null,
        );
      }
      if (response.correct)
        try {
          await onEarned?.();
        } catch {
          if (mounted.current && request.current === currentRequest)
            setNotice(
              "Результат сохранён. Общий баланс обновится при следующем подключении.",
            );
        }
    } catch (error) {
      if (mounted.current && request.current === currentRequest)
        setReaderError(message(error));
    } finally {
      if (mounted.current && request.current === currentRequest) {
        pending.current = false;
        setSubmitting(false);
      }
    }
  }
  if (materialId)
    return (
      <section
        className="learning learning-reader"
        aria-busy={!material && !readerError}
      >
        <button
          type="button"
          className="learning-back"
          onClick={() => setMaterialId("")}
        >
          ← Материалы
        </button>
        {readerError && (
          <div className="learning-error" role="alert">
            <p>{readerError}</p>
            {!material && (
              <button
                type="button"
                onClick={() => setAttempt((value) => value + 1)}
              >
                Повторить загрузку
              </button>
            )}
          </div>
        )}
        {!material && !readerError && (
          <p className="learning-muted" role="status">
            Загружаем материал…
          </p>
        )}
        {material && (
          <>
            <p className="learning-eyebrow">
              {categoryLabel(material.category)}
              {material.audience === "staff" ? " · Для сотрудников" : ""}
            </p>
            <h1 ref={heading} tabIndex={-1}>
              {material.title}
            </h1>
            <p className="learning-muted">{material.description}</p>
            {material.demo && (
              <p className="learning-demo">
                Демонстрационный материал · уточняй актуальные условия у HR.
              </p>
            )}
            <article className="learning-content">
              {material.blocks.map((block, index) =>
                block.type === "heading" ? (
                  <h2 key={index}>{block.text}</h2>
                ) : block.type === "text" ? (
                  <p key={index}>{block.text}</p>
                ) : (
                  <LearningMedia
                    key={`${material.id}:${index}:${block.mediaId}`}
                    block={block}
                    loadMedia={loadMedia}
                  />
                ),
              )}
            </article>
            {material.quiz && (
              <section
                className="learning-quiz"
                aria-labelledby="learning-quiz-heading"
              >
                <p className="learning-eyebrow">ЗАКРЕПИ ЗНАНИЯ</p>
                <h2 id="learning-quiz-heading">Короткий тест</h2>
                <p className="learning-muted">
                  {material.completion
                    ? `Тест уже пройден: начислено ${material.completion.awardedPoints} баллов. Повторная попытка — для тренировки.`
                    : `За все правильные ответы — ${material.quiz.points} баллов один раз. Ошибки не уменьшают баланс.`}
                </p>
                <form
                  onSubmit={(event) => {
                    void complete(event);
                  }}
                >
                  {material.quiz.questions.map((question, index) => (
                    <fieldset key={question.id} disabled={submitting}>
                      <legend>
                        {index + 1}. {question.text}
                      </legend>
                      {question.options.map((option) => (
                        <label
                          key={option.id}
                          className={
                            answers[question.id] === option.id
                              ? "learning-selected"
                              : ""
                          }
                        >
                          <input
                            type="radio"
                            name={`material-${material.id}-${question.id}`}
                            value={option.id}
                            checked={answers[question.id] === option.id}
                            onChange={() => {
                              setAnswers((current) => ({
                                ...current,
                                [question.id]: option.id,
                              }));
                              setResult(null);
                            }}
                          />
                          <span>{option.text}</span>
                        </label>
                      ))}
                    </fieldset>
                  ))}
                  <button
                    type="submit"
                    className="learning-primary"
                    disabled={
                      submitting ||
                      material.quiz.questions.some(
                        (question) => !answers[question.id],
                      )
                    }
                  >
                    {submitting
                      ? "Проверяем…"
                      : material.completion
                        ? "Проверить ещё раз"
                        : "Проверить ответы"}
                  </button>
                </form>
                {result && (
                  <div
                    className={`learning-result ${result.correct ? "is-correct" : ""}`}
                    role="status"
                  >
                    <h3 ref={resultHeading} tabIndex={-1}>
                      {result.correct
                        ? result.alreadyCompleted
                          ? "Верно · без повторного начисления"
                          : `Верно! +${result.pointsAwarded} баллов`
                        : "Попробуй ещё раз"}
                    </h3>
                    {result.errors.map((error, index) => (
                      <p key={index}>{error}</p>
                    ))}
                    {result.correct && (
                      <>
                        <p>
                          Баланс: <strong>{result.balance} баллов</strong>
                        </p>
                        {result.explanations?.map((item) => (
                          <p key={item.questionId}>{item.text}</p>
                        ))}
                      </>
                    )}
                  </div>
                )}
                {notice && (
                  <p className="learning-muted" role="status">
                    {notice}
                  </p>
                )}
              </section>
            )}
          </>
        )}
      </section>
    );
  const visible = (materials ?? []).filter(
    (item) => category === "all" || item.category === category,
  );
  return (
    <section className="learning" aria-labelledby="learning-heading">
      <p className="learning-eyebrow">УЗНАВАЙ НОВОЕ</p>
      <h1 id="learning-heading">Материалы</h1>
      <p className="learning-muted">
        История компании, знакомство с профессиями и полезное о практике.
      </p>
      <nav className="learning-categories" aria-label="Категории материалов">
        {categories.map((item) => (
          <button
            type="button"
            key={item.id}
            aria-pressed={category === item.id}
            className={category === item.id ? "learning-active" : ""}
            onClick={() => setCategory(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      {listError ? (
        <div className="learning-error" role="alert">
          <p>{listError}</p>
          <button
            type="button"
            onClick={() => setAttempt((value) => value + 1)}
          >
            Повторить загрузку
          </button>
        </div>
      ) : materials === null ? (
        <p className="learning-muted" role="status">
          Загружаем материалы…
        </p>
      ) : visible.length ? (
        <div className="learning-list">
          {visible.map((item) => (
            <button
              type="button"
              className="learning-card"
              key={item.id}
              onClick={() => setMaterialId(item.id)}
            >
              <span className="learning-eyebrow">
                {categoryLabel(item.category)}
                {item.audience === "staff" ? " · Для сотрудников" : ""}
              </span>
              <h2>{item.title}</h2>
              <p>{item.description}</p>
              <span className="learning-card-footer">
                {item.completion
                  ? `✓ Пройдено · ${item.completion.awardedPoints} баллов`
                  : item.questionCount
                    ? `Тест · +${item.points} баллов`
                    : "Читать материал"}
                <span aria-hidden="true">→</span>
              </span>
              {item.demo && <small>Демонстрационный пример</small>}
            </button>
          ))}
        </div>
      ) : (
        <p className="learning-empty">
          Опубликованных материалов в этой категории пока нет.
        </p>
      )}
    </section>
  );
}

function LearningMedia({
  block,
  loadMedia,
}: {
  block: Extract<MaterialBlock, { type: "video" | "image" }>;
  loadMedia?: MediaLoader;
}) {
  const [url, setUrl] = useState(""),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0);
  const video = useRef<HTMLVideoElement>(null),
    activeUrl = useRef("");
  useEffect(() => {
    let live = true,
      objectUrl = "";
    setUrl("");
    setError("");
    if (!loadMedia) {
      setError("Загрузка файла пока недоступна.");
      return;
    }
    void loadMedia(block.mediaId)
      .then((blob) => {
        if (!live) return;
        objectUrl = URL.createObjectURL(blob);
        activeUrl.current = objectUrl;
        setUrl(objectUrl);
      })
      .catch((failure) => {
        if (live) setError(message(failure));
      });
    const preview = video.current;
    return () => {
      live = false;
      if (preview) {
        preview.pause();
        preview.removeAttribute("src");
        preview.load();
      }
      if (objectUrl && activeUrl.current === objectUrl) {
        URL.revokeObjectURL(objectUrl);
        activeUrl.current = "";
      }
    };
  }, [block.mediaId, loadMedia, attempt]);
  function mediaError(text: string) {
    if (!url || activeUrl.current !== url) return;
    const preview = video.current;
    if (preview) {
      preview.pause();
      preview.removeAttribute("src");
      preview.load();
    }
    URL.revokeObjectURL(url);
    activeUrl.current = "";
    setUrl("");
    setError(text);
  }
  return (
    <figure className="learning-media">
      {block.type === "video" ? (
        <>
          <video
            ref={video}
            src={url || undefined}
            controls
            playsInline
            preload="metadata"
            hidden={!url}
            aria-label={block.title || "Видео материала"}
            onError={() =>
              mediaError(
                "Браузер не смог воспроизвести файл. Попробуй загрузить его ещё раз.",
              )
            }
          />
          {block.title && <figcaption>{block.title}</figcaption>}
        </>
      ) : (
        url && (
          <img
            src={url}
            alt={block.alt}
            onError={() =>
              mediaError(
                "Не удалось показать изображение. Попробуй загрузить его ещё раз.",
              )
            }
          />
        )
      )}
      {error ? (
        <div className="learning-error" role="alert">
          <p>{error}</p>
          {loadMedia && (
            <button
              type="button"
              onClick={() => setAttempt((value) => value + 1)}
            >
              Загрузить файл ещё раз
            </button>
          )}
        </div>
      ) : (
        !url && (
          <p className="learning-muted" role="status">
            Загружаем файл…
          </p>
        )
      )}
    </figure>
  );
}
export default Learning;
