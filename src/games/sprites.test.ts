import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import {
  getSprite,
  presentationErrors,
  spriteAssets,
  spriteFor,
} from "./sprites";
import type { GamePresentation, SignalPuzzle, Task } from "./types";

const catalog = JSON.parse(
  readFileSync(new URL("../../server/catalog.json", import.meta.url), "utf8"),
) as { tasks: Task[] };

function presentation(): GamePresentation {
  return {
    schemaVersion: 1,
    sprites: { preview: "automation-bottle-circle" },
    scene: {
      width: 358,
      height: 441,
      objects: [
        {
          id: "bottle",
          spriteId: "automation-bottle-circle",
          x: 81,
          y: 29,
          width: 96,
          height: 96,
          layer: 2,
        },
      ],
    },
  };
}

test("sprite library consists of distinct local transparent modules at documented resolution", () => {
  assert.equal(spriteAssets.length, 16);
  assert.equal(new Set(spriteAssets.map((asset) => asset.id)).size, 16);
  assert.equal(new Set(spriteAssets.map((asset) => asset.src)).size, 16);
  for (const asset of spriteAssets) {
    assert.match(asset.src, /^\/assets\/games-v5\/[a-z0-9-]+\.png$/);
    assert.equal(asset.width, 96, asset.id);
    assert.equal(asset.height, 96, asset.id);
    const file = new URL(`../../public${asset.src}`, import.meta.url);
    const png = readFileSync(file);
    assert.ok(statSync(file).size > 1000, asset.id);
    assert.deepEqual(
      [...png.subarray(0, 8)],
      [137, 80, 78, 71, 13, 10, 26, 10],
    );
    assert.equal(png.readUInt32BE(16), asset.pixelWidth, asset.id);
    assert.equal(png.readUInt32BE(20), asset.pixelHeight, asset.id);
    assert.equal(asset.pixelWidth, 192, asset.id);
    assert.equal(asset.pixelHeight, 192, asset.id);
    assert.equal(png[25], 6, `${asset.id}: RGBA cutout`);
    assert.equal(getSprite(asset.id)?.src, asset.src);
  }
});

test("published level presentation only references installed modules", () => {
  const configured = catalog.tasks.filter((task) => task.presentation);
  assert.ok(configured.length > 0, "catalog must publish configured levels");
  for (const task of configured) {
    assert.deepEqual(presentationErrors(task.presentation), [], task.id);
  }
});

test("an editor can override roles and clone a level without deriving its artwork from the level id", () => {
  const source = catalog.tasks.find((task) => task.game === "signal")!;
  const sourcePuzzle = source.puzzle as SignalPuzzle;
  const clone: Task = {
    ...source,
    id: "editor-new-level",
    level: 107,
    puzzle: {
      ...sourcePuzzle,
      stream: [...sourcePuzzle.stream].reverse(),
      maxRules: sourcePuzzle.maxRules + 1,
    },
    presentation: {
      ...presentation(),
      sprites: {
        preview: "mechanics-gear-red",
        unknown: "laboratory-tube-gold",
      },
    },
  };
  assert.notEqual(clone.id, source.id);
  assert.notDeepEqual(clone.puzzle, source.puzzle);
  assert.deepEqual(presentationErrors(clone.presentation), []);
  assert.equal(
    spriteFor(clone, "preview", "automation-bottle-circle"),
    "mechanics-gear-red",
  );
  assert.equal(
    spriteFor(clone, "unknown", "laboratory-tube-red"),
    "laboratory-tube-gold",
  );
  assert.equal(
    spriteFor(clone, "missing-role", "automation-scanner"),
    "automation-scanner",
  );
  assert.equal(
    spriteFor({}, "preview", "automation-scanner"),
    "automation-scanner",
  );
});

test("malformed scene data is rejected before rendering a level preview", () => {
  const invalidValues: unknown[] = [
    null,
    [],
    "scene",
    { schemaVersion: 2, sprites: {} },
  ];
  const badRole = presentation();
  badRole.sprites.preview = "https://example.invalid/remote.png";
  invalidValues.push(badRole);
  for (const mutate of [
    (p: GamePresentation) => {
      p.scene!.width = 0;
    },
    (p: GamePresentation) => {
      p.scene!.height = Infinity;
    },
    (p: GamePresentation) => {
      p.scene!.objects[0].spriteId = "missing-module";
    },
    (p: GamePresentation) => {
      p.scene!.objects[0].x = NaN;
    },
    (p: GamePresentation) => {
      p.scene!.objects[0].y = Infinity;
    },
    (p: GamePresentation) => {
      p.scene!.objects[0].width = -2;
    },
    (p: GamePresentation) => {
      p.scene!.objects[0].height = 0;
    },
    (p: GamePresentation) => {
      p.scene!.objects[0].rotation = NaN;
    },
    (p: GamePresentation) => {
      p.scene!.objects[0].layer = 1.5;
    },
    (p: GamePresentation) => {
      p.scene!.objects[0].layer = 101;
    },
    (p: GamePresentation) => {
      p.scene!.objects.push({ ...p.scene!.objects[0] });
    },
    (p: GamePresentation) => {
      p.scene!.objects = Array.from({ length: 201 }, (_, index) => ({
        ...p.scene!.objects[0],
        id: `object-${index}`,
      }));
    },
  ]) {
    const value = presentation();
    mutate(value);
    invalidValues.push(value);
  }
  for (const value of invalidValues) {
    assert.ok(presentationErrors(value).length > 0, JSON.stringify(value));
  }
  assert.deepEqual(presentationErrors(presentation()), []);
});

test("an uploaded module registers without renderer changes and rejects executable URLs atomically", async () => {
  const { registerSpriteAssets } = await import("./sprites");
  const uploaded = {
    id: "admin-new-asset",
    kind: "general",
    src: "/api/game-assets/admin-new-asset/",
    width: 96,
    height: 96,
    pixelWidth: 192,
    pixelHeight: 192,
  };
  registerSpriteAssets({ schemaVersion: 1, sprites: [uploaded] });
  assert.equal(getSprite(uploaded.id)?.src, uploaded.src);
  assert.deepEqual(
    presentationErrors({ schemaVersion: 1, sprites: { source: uploaded.id } }),
    [],
  );
  for (const src of [
    "https://foreign.invalid/asset.png",
    "javascript:alert(1)",
    "//foreign.invalid/x",
    "/api/game-assets/../secret/",
  ]) {
    assert.throws(() =>
      registerSpriteAssets({
        schemaVersion: 1,
        sprites: [{ ...uploaded, id: "rejected-asset", src }],
      }),
    );
    assert.equal(getSprite("rejected-asset"), undefined);
  }
});
