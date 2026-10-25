/* A schema-driven form. Values are data; never evaluated or inserted as HTML. */
(() => {
  const labels = {
    id: "Постоянный ID",
    title: "Название",
    text: "Текст",
    type: "Тип блока",
    mediaId: "Медиафайл",
    alt: "Описание изображения",
    points: "Баллы",
    questions: "Вопросы",
    options: "Варианты ответа",
    correctOptionId: "Правильный вариант",
    explanation: "Объяснение",
    positive: "Правильные проверочные решения",
    negative: "Ошибочные проверочные решения",
    schemaVersion: "Версия формата",
    sprites: "Роли и спрайты",
    scene: "Сцена",
    objects: "Объекты",
    spriteId: "Спрайт",
    role: "Роль",
    width: "Ширина",
    height: "Высота",
    rotation: "Поворот",
    layer: "Слой",
    label: "Подпись",
    stream: "Поток упаковок",
    color: "Цвет",
    marked: "Метка",
    allowedConditions: "Доступные условия",
    outputs: "Выходы",
    rule: "Условие сортировки",
    maxRules: "Максимум правил",
    source: "Привод",
    target: "Цель",
    direction: "Направление вращения",
    maxGears: "Максимум шестерён",
    maxBelts: "Максимум ремней",
    beltLinks: "Разрешённые ременные связи",
    from: "Откуда",
    to: "Куда",
    samples: "Образцы",
    name: "Название",
    properties: "Свойства",
    tests: "Исследования",
    observations: "Наблюдаемые свойства",
    batches: "Партии",
    product: "Продукт",
    cells: "Клетки упаковки",
    reserved: "Зарезервирована",
    location: "Место хранения",
    order: "Заказ",
    quantity: "Количество",
    start: "Начало маршрута",
    warehouse: "Склад",
    answers: "Ответы",
    metrics: "Показатели",
    value: "Текущее значение",
    previous: "Предыдущее значение",
    unit: "Единицы",
    series: "Измерения",
    time: "Время",
    factId: "Связанный факт",
    historyFactId: "Факт графика",
    scheme: "Схема",
    nodes: "Узлы",
    flows: "Потоки",
    journal: "Журнал событий",
    detail: "Подробности",
    checks: "Проверки",
    description: "Описание",
    result: "Результат",
    facts: "Факты",
    conclusion: "Варианты вывода",
    observedChange: "Наблюдаемое изменение",
    nextStep: "Следующий шаг",
    responsible: "Ответственный",
    hints: "Исследовательские подсказки",
    localizationPaths: "Альтернативные достаточные пути",
    causeFacts: "Причинные факты",
    contradictoryFacts: "Противоречащие факты",
    explanationText: "Объяснение результата",
    outcome: "Последствия",
    summary: "Итог",
    before: "До",
    after: "После",
    assessment: "Оценка по критериям",
    localization: "Локализация",
    cause: "Причина",
    evidence: "Основания",
    sampleId: "Выбранный образец",
    placements: "Размещение",
    batchId: "ID партии",
    rotated: "Повёрнута",
    route: "Маршрут",
    gears: "Шестерни",
    belts: "Ремни",
    rules: "Правила алгоритма",
    condition: "Условие",
    output: "Выход",
  };
  const el = (tag, text) => {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const defaults = (s) =>
    s.default ??
    (s.enum
      ? s.enum[0]
      : s.type === "array"
        ? []
        : s.type === "object"
          ? Object.fromEntries(
              Object.entries(s.properties || {}).map(([k, v]) => [
                k,
                defaults(v),
              ]),
            )
          : s.type === "block"
            ? { type: "text", text: "" }
            : s.type === "map"
              ? {}
              : s.type === "boolean"
                ? false
                : s.type === "integer" || s.type === "number"
                  ? 0
                  : "");
  const boot = () =>
    document
      .querySelectorAll(".content-constructor:not([data-ready])")
      .forEach((root) => {
        root.dataset.ready = "1";
        const input = root.querySelector("textarea"),
          host = root.querySelector(".constructor-fields");
        let schema, value;
        try {
          schema = JSON.parse(input.dataset.schema);
          value = JSON.parse(input.value || "null") ?? defaults(schema);
        } catch {
          host.textContent =
            "Не удалось прочитать сохранённую структуру. Исправьте данные перед сохранением.";
          return;
        }
        input.hidden = true;
        const sync = () => {
          input.value = JSON.stringify(value);
          input.dispatchEvent(new Event("change", { bubbles: true }));
        };
        function field(s, v, set, label) {
          const box = el("div");
          box.className = "constructor-field";
          if (label) box.append(el("label", labels[label] || label));
          const isBlock = s.type === "block";
          if (s.type === "block") {
            s = {
              type: "object",
              properties: {
                type: { enum: ["text", "heading", "image", "video"] },
                ...(v?.type === "image"
                  ? {
                      mediaId: {
                        type: "string",
                        ...((schema.media || []).filter(
                          (m) => m.kind === "image",
                        ).length
                          ? {
                              enum: schema.media
                                .filter((m) => m.kind === "image")
                                .map((m) => m.id),
                            }
                          : {}),
                      },
                      alt: { type: "string" },
                    }
                  : v?.type === "video"
                    ? {
                        mediaId: {
                          type: "string",
                          ...((schema.media || []).filter(
                            (m) => m.kind === "video",
                          ).length
                            ? {
                                enum: schema.media
                                  .filter((m) => m.kind === "video")
                                  .map((m) => m.id),
                              }
                            : {}),
                        },
                        title: { type: "string" },
                      }
                    : { text: { type: "string" } }),
              },
            };
          }
          if (s.enum) {
            const select = el("select");
            s.enum.forEach((x, i) => {
              const option = el("option", String(x));
              option.value = String(i);
              option.selected = x === v;
              select.append(option);
            });
            select.onchange = () => {
              set(s.enum[Number(select.value)]);
              sync();
            };
            box.append(select);
          } else if (s.type === "object") {
            const data =
              v && typeof v === "object" && !Array.isArray(v) ? v : {};
            const inner = el("div");
            inner.className = "constructor-object";
            const properties = { ...s.properties };
            Object.keys(data).forEach((k) => {
              if (!properties[k])
                properties[k] = {
                  type:
                    typeof data[k] === "number"
                      ? "number"
                      : Array.isArray(data[k])
                        ? "array"
                        : typeof data[k] === "object"
                          ? "map"
                          : "string",
                  items: { type: "string" },
                  values: { type: "string" },
                };
            });
            Object.entries(properties).forEach(([k, definition]) => {
              const child =
                k === "correctOptionId" &&
                Array.isArray(data.options) &&
                data.options.length
                  ? { enum: data.options.map((o) => o.id) }
                  : definition;
              const has = Object.hasOwn(data, k);
              const wrap = el("div");
              if (!has) {
                const add = el("button", "Добавить поле: " + (labels[k] || k));
                add.type = "button";
                add.onclick = () => {
                  data[k] = defaults(child);
                  set(data);
                  sync();
                  redraw();
                };
                wrap.append(add);
              } else
                wrap.append(
                  field(
                    child,
                    data[k],
                    (x) => {
                      data[k] = x;
                      set(data);
                      if (k === "type" && isBlock) {
                        const type = data.type;
                        for (const key of Object.keys(data))
                          if (key !== "type") delete data[key];
                        if (type === "image") {
                          data.mediaId = "";
                          data.alt = "";
                        } else if (type === "video") {
                          data.mediaId = "";
                          data.title = "";
                        } else data.text = "";
                        redraw();
                      }
                    },
                    k,
                  ),
                );
              inner.append(wrap);
            });
            box.append(inner);
          } else if (s.type === "array" || s.type === "map") {
            const data =
              s.type === "array"
                ? Array.isArray(v)
                  ? v
                  : []
                : v && typeof v === "object"
                  ? v
                  : {};
            Object.entries(data).forEach(([key, item], index) => {
              const row = el("details");
              row.open = true;
              row.append(
                el("summary", s.type === "array" ? "Блок " + (index + 1) : key),
              );
              row.append(
                field(
                  s.type === "array" ? s.items : s.values,
                  item,
                  (x) => {
                    data[key] = x;
                    set(data);
                  },
                  "",
                ),
              );
              const remove = el("button", "Удалить");
              remove.type = "button";
              remove.onclick = () => {
                if (Array.isArray(data)) data.splice(index, 1);
                else delete data[key];
                set(data);
                sync();
                redraw();
              };
              row.append(remove);
              if (Array.isArray(data) && index) {
                const up = el("button", "Выше");
                up.type = "button";
                up.onclick = () => {
                  [data[index - 1], data[index]] = [
                    data[index],
                    data[index - 1],
                  ];
                  set(data);
                  sync();
                  redraw();
                };
                row.append(up);
              }
              box.append(row);
            });
            let key;
            if (s.type === "map") {
              key = el("input");
              key.placeholder = "Новый ID / роль";
              box.append(key);
            }
            const add = el(
              "button",
              "Добавить " + (s.type === "array" ? "элемент" : "ключ"),
            );
            add.type = "button";
            add.onclick = () => {
              if (Array.isArray(data)) data.push(defaults(s.items));
              else {
                if (
                  !key.value.trim() ||
                  ["__proto__", "constructor", "prototype"].includes(
                    key.value.trim(),
                  ) ||
                  Object.hasOwn(data, key.value.trim())
                )
                  return;
                data[key.value.trim()] = defaults(s.values);
              }
              set(data);
              sync();
              redraw();
            };
            box.append(add);
          } else if (s.type === "boolean") {
            const control = el("input");
            control.type = "checkbox";
            control.checked = Boolean(v);
            control.onchange = () => {
              set(control.checked);
              sync();
            };
            box.append(control);
          } else {
            const control = el(s.type === "string" ? "textarea" : "input");
            if (s.type !== "string") {
              control.type = "number";
              control.step = s.type === "integer" ? "1" : "any";
            }
            control.value = v ?? "";
            control.oninput = () => {
              set(
                s.type === "integer" || s.type === "number"
                  ? Number(control.value)
                  : control.value,
              );
              sync();
            };
            box.append(control);
          }
          const caption = box.firstElementChild;
          if (caption?.tagName === "LABEL") {
            const control = [...box.children].find((e) =>
              ["INPUT", "TEXTAREA", "SELECT"].includes(e.tagName),
            );
            if (control)
              control.setAttribute("aria-label", caption.textContent);
          }
          return box;
        }
        function redraw() {
          host.replaceChildren(
            field(
              schema,
              value,
              (x) => {
                value = x;
              },
              "",
            ),
          );
        }
        redraw();
        root.closest("form")?.addEventListener("submit", sync);
      });
  document.addEventListener("DOMContentLoaded", boot);
  document.addEventListener("formset:added", boot);
  boot();
})();
