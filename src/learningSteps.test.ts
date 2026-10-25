import { test } from "node:test";
import assert from "node:assert/strict";
import { readingSteps } from "./learning/readingSteps";
import type { MaterialBlock } from "./learning/types";

test("reading pairs headings with content and reveals paragraphs individually", () => {
  assert.deepEqual(
    readingSteps([
      { type: "heading", text: "Знакомство" },
      { type: "text", text: "Первый абзац.\n\nВторой абзац." },
      { type: "heading", text: "Команда" },
      { type: "image", mediaId: "team", alt: "Команда" },
      { type: "video", mediaId: "tour", title: "Экскурсия" },
    ]),
    [
      [
        { type: "heading", text: "Знакомство" },
        { type: "text", text: "Первый абзац." },
      ],
      [{ type: "text", text: "Второй абзац." }],
      [
        { type: "heading", text: "Команда" },
        { type: "image", mediaId: "team", alt: "Команда" },
      ],
      [{ type: "video", mediaId: "tour", title: "Экскурсия" }],
    ],
  );
});

test("a long unformatted block becomes short passages without losing text", () => {
  const text = "Познакомься с командой и узнай, как устроена работа. "
    .repeat(65)
    .trim();
  const steps = readingSteps([{ type: "text", text }]);
  const parts = steps
    .flat()
    .filter(
      (block): block is Extract<MaterialBlock, { type: "text" }> =>
        block.type === "text",
    );
  assert.ok(parts.length > 1);
  assert.ok(parts.every((block) => block.text.length <= 600));
  assert.equal(parts.map((block) => block.text).join(" "), text);
});

test("empty content and trailing headings retain their order without extra blank steps", () => {
  assert.deepEqual(readingSteps([]), []);
  assert.deepEqual(readingSteps([{ type: "text", text: "\n " }]), []);
  const blocks: MaterialBlock[] = [
    { type: "heading", text: "Начало" },
    { type: "text", text: "Текст" },
    { type: "heading", text: "Конец" },
  ];
  assert.deepEqual(readingSteps(blocks), [blocks]);
});
