import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import type { ApiClient, MediaLoader } from "../api";
import type {
  Material,
  MaterialBlock,
  MaterialCategory,
  MaterialResult,
  MaterialSummary,
} from "./types";
import { careerLabel } from "../games/careerLabels";
import { readingSteps } from "./readingSteps";
import "./learning.css";

export interface LearningProps {
  client: ApiClient;
  onEarned?: () => void | Promise<void>;
  initialMaterialId?: string;
  loadMedia?: MediaLoader;
  historyCareerExplanation?: string;
  onHistoryCareer?: () => void;
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
  historyCareerExplanation,
  onHistoryCareer,
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
  const [visibleSteps, setVisibleSteps] = useState(1),
    [quizStarted, setQuizStarted] = useState(false),
    [questionIndex, setQuestionIndex] = useState(0);
  const steps = useMemo(
    () => readingSteps(material?.blocks ?? []),
    [material?.blocks],
  );
  const readingComplete = visibleSteps >= steps.length;
  const question = material?.quiz?.questions[questionIndex];
  const lastQuestion =
    questionIndex === (material?.quiz?.questions.length ?? 0) - 1;
  const pending = useRef(false),
    mounted = useRef(true),
    request = useRef(0),
    heading = useRef<HTMLHeadingElement>(null),
    latestStep = useRef<HTMLDivElement>(null),
    questionHeading = useRef<HTMLSpanElement>(null),
    quizHeading = useRef<HTMLHeadingElement>(null),
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
    setVisibleSteps(1);
    setQuizStarted(false);
    setQuestionIndex(0);
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
    if (visibleSteps > 1) {
      latestStep.current?.scrollIntoView({ block: "start" });
      latestStep.current?.focus({ preventScroll: true });
    }
  }, [visibleSteps]);
  useEffect(() => {
    if (quizStarted && !result) {
      questionHeading.current?.scrollIntoView({ block: "center" });
      questionHeading.current?.focus({ preventScroll: true });
    }
  }, [quizStarted, questionIndex, result]);
  useEffect(() => {
    if (result) {
      resultHeading.current?.scrollIntoView({ block: "center" });
      resultHeading.current?.focus({ preventScroll: true });
    }
  }, [result]);
  async function complete(event: FormEvent) {
    event.preventDefault();
    if (
      !material?.quiz ||
      pending.current ||
      !quizStarted ||
      !readingComplete ||
      !lastQuestion ||
      material.quiz.questions.some((item) => !answers[item.id])
    )
      return;
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
  function startQuiz() {
    setAnswers({});
    setResult(null);
    setReaderError("");
    setNotice("");
    setQuestionIndex(0);
    setQuizStarted(true);
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
            <p className="learning-progress" role="status">
              {readingComplete
                ? "Материал открыт полностью"
                : `Часть ${visibleSteps} из ${steps.length}`}
            </p>
            <article className="learning-content" aria-label="Текст материала">
              {steps.slice(0, visibleSteps).map((blocks, index) => (
                <div
                  className="learning-passage"
                  key={`${material.id}:${index}`}
                  ref={index === visibleSteps - 1 ? latestStep : undefined}
                  tabIndex={-1}
                  role="group"
                  aria-label={`Часть ${index + 1}`}
                >
                  {blocks.map((block, blockIndex) =>
                    block.type === "heading" ? (
                      <h2 key={blockIndex}>{block.text}</h2>
                    ) : block.type === "text" ? (
                      <p key={blockIndex}>{block.text}</p>
                    ) : (
                      <LearningMedia
                        key={blockIndex}
                        block={block}
                        loadMedia={loadMedia}
                      />
                    ),
                  )}
                </div>
              ))}
            </article>
            {!readingComplete && (
              <button
                type="button"
                className="learning-primary"
                onClick={() =>
                  setVisibleSteps((count) => Math.min(count + 1, steps.length))
                }
              >
                Читать дальше →
              </button>
            )}
            {material.quiz && readingComplete && (
              <section
                className="learning-quiz"
                aria-labelledby="learning-quiz-heading"
              >
                <p className="learning-eyebrow">ЗАКРЕПИ ЗНАНИЯ</p>
                <h2 id="learning-quiz-heading" ref={quizHeading} tabIndex={-1}>
                  Короткий тест
                </h2>
                <p className="learning-muted">
                  {material.completion
                    ? `Тест уже пройден: начислено ${material.completion.awardedPoints} баллов. Повторная попытка — для тренировки.`
                    : `За все правильные ответы — ${material.quiz.points} баллов один раз. Ошибки не уменьшают баланс.`}
                </p>
                {!quizStarted && (
                  <button
                    type="button"
                    className="learning-primary"
                    onClick={startQuiz}
                  >
                    Начать тест
                  </button>
                )}
                {quizStarted && question && !result && (
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (submitting || !answers[question.id]) return;
                      if (lastQuestion) void complete(event);
                      else setQuestionIndex((index) => index + 1);
                    }}
                  >
                    <p className="learning-progress" role="status">
                      Вопрос {questionIndex + 1} из{" "}
                      {material.quiz.questions.length}
                    </p>
                    <fieldset key={question.id} disabled={submitting}>
                      <legend>
                        <span ref={questionHeading} tabIndex={-1}>
                          {question.text}
                        </span>
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
                    <div className="learning-step-actions">
                      {questionIndex > 0 && (
                        <button
                          type="button"
                          className="learning-secondary"
                          disabled={submitting}
                          onClick={() => setQuestionIndex((index) => index - 1)}
                        >
                          ← Назад
                        </button>
                      )}
                      <button
                        type="submit"
                        className="learning-primary"
                        disabled={submitting || !answers[question.id]}
                      >
                        {submitting
                          ? "Проверяем…"
                          : lastQuestion
                            ? "Проверить ответы"
                            : "Далее →"}
                      </button>
                    </div>
                  </form>
                )}
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
                        {material.id === "ochakovo-history" &&
                          onHistoryCareer && (
                            <>
                              {historyCareerExplanation && (
                                <p>{historyCareerExplanation}</p>
                              )}
                              <button
                                type="button"
                                className="button"
                                onClick={onHistoryCareer}
                              >
                                {careerLabel("technology")}
                              </button>
                            </>
                          )}
                      </>
                    )}
                    <button
                      type="button"
                      className="learning-primary"
                      disabled={submitting}
                      onClick={startQuiz}
                    >
                      {result.correct ? "Пройти ещё раз" : "Попробовать снова"}
                    </button>
                  </div>
                )}
                {quizStarted && (
                  <button
                    type="button"
                    className="learning-back"
                    disabled={submitting}
                    onClick={() => {
                      setQuizStarted(false);
                      setQuestionIndex(0);
                      setResult(null);
                      heading.current?.scrollIntoView({ block: "start" });
                      heading.current?.focus({ preventScroll: true });
                    }}
                  >
                    ↑ Перечитать материал
                  </button>
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
