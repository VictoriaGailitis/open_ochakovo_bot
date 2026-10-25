import type { MaterialBlock } from "./types";

const MAX_PASSAGE_LENGTH = 600;

/** Keep paragraphs and sentence boundaries; even one large editor block is paced. */
function passages(text: string): string[] {
  return text.split(/\n+/).flatMap((paragraph) => {
    let remaining = paragraph.trim();
    const parts: string[] = [];
    while (remaining.length > MAX_PASSAGE_LENGTH) {
      const window = remaining.slice(0, MAX_PASSAGE_LENGTH + 1);
      const sentenceEnds = [...window.matchAll(/[.!?…](?:[»”"])?\s+/g)];
      const sentence = sentenceEnds.at(-1);
      const sentenceEnd = sentence
        ? sentence.index! + sentence[0].trimEnd().length
        : 0;
      const wordEnd = window.lastIndexOf(" ");
      const end =
        sentenceEnd >= MAX_PASSAGE_LENGTH / 2
          ? sentenceEnd
          : wordEnd > 0
            ? wordEnd
            : MAX_PASSAGE_LENGTH;
      parts.push(remaining.slice(0, end).trim());
      remaining = remaining.slice(end).trim();
    }
    if (remaining) parts.push(remaining);
    return parts;
  });
}

export function readingSteps(blocks: MaterialBlock[]): MaterialBlock[][] {
  const steps: MaterialBlock[][] = [];
  let headings: MaterialBlock[] = [];
  for (const block of blocks) {
    if (block.type === "heading") {
      headings.push(block);
      continue;
    }
    const content: MaterialBlock[] =
      block.type === "text"
        ? passages(block.text).map((text) => ({ type: "text", text }))
        : [block];
    for (const part of content) {
      steps.push([...headings, part]);
      headings = [];
    }
  }
  if (headings.length) {
    if (steps.length) steps[steps.length - 1].push(...headings);
    else steps.push(headings);
  }
  return steps;
}
