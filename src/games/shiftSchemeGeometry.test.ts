import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import type { ShiftPuzzle, ShiftSchemeNode, ShiftSchemeFlow } from "./ShiftTypes";
import { shiftSchemeGeometry } from "./shiftSchemeGeometry";

const node = (id: string, x: number, y: number): ShiftSchemeNode => ({
  id, position: { x, y }, display: "card", label: id, value: 10, unit: "шт.", factId: "fact-" + id,
});
const flow = (id: string, from: string, to: string): ShiftSchemeFlow => ({
  id, from, to, label: id, factId: "fact-" + id,
});
const catalog = JSON.parse(readFileSync(new URL("../../server/catalog.json", import.meta.url), "utf8"));
const baseline = catalog.tasks.find((task: { id: string }) => task.id === "shift-1").puzzle as ShiftPuzzle;

test("both existing shifts draw every authored flow and retain the design's pipe and buffer positions", () => {
  for (const task of catalog.tasks.filter((task: { game: string }) => task.game === "shift")) {
    const geometry = shiftSchemeGeometry(task.puzzle.scheme);
    assert.deepEqual(geometry.flows.map(({ flow }) => flow.id), task.puzzle.scheme.flows.map((flow: ShiftSchemeFlow) => flow.id));
    assert.equal(geometry.flows[0].path, "M73.5,89 L73.5,112");
    assert.deepEqual(geometry.nodes.find(({ node }) => node.id === "packaging")?.x, 195);
  }
  assert.deepEqual(shiftSchemeGeometry(baseline.scheme).queues[0].dots,
    [95,117,139,161].map((x) => ({ x, y: 220 })));
});

test("legacy levels without authored positions keep their defaults without mutating their puzzle", () => {
  const legacy = { ...baseline.scheme, nodes: baseline.scheme.nodes.map((node) => ({ ...node, position: undefined })) };
  const before = JSON.stringify(legacy);
  const old = shiftSchemeGeometry(legacy), current = shiftSchemeGeometry(baseline.scheme);
  assert.deepEqual(old.nodes.map(({ x, y, display }) => ({ x, y, display })),
    current.nodes.map(({ x, y, display }) => ({ x, y, display })));
  assert.deepEqual(old.flows.map(({ path }) => path), current.flows.map(({ path }) => path));
  assert.equal(JSON.stringify(legacy), before);
});

test("a new graph with unrelated IDs and different branching follows its authored nodes", () => {
  const scheme = { nodes: [node("mixer",20,20), node("filter",200,130), node("outlet",20,200)],
    flows: [flow("to-filter","mixer","filter"),flow("to-outlet","mixer","outlet")] };
  const geometry = shiftSchemeGeometry(scheme);
  assert.equal(geometry.flows.length,2);
  assert.equal(geometry.flows[0].points[0].x,145); // Right edge of source card.
  assert.equal(geometry.flows[0].points.at(-1)?.x,200); // Left edge of target card.
  assert.notEqual(geometry.flows[0].path,geometry.flows[1].path);
  const moved = shiftSchemeGeometry({ ...scheme, nodes: scheme.nodes.map((n) => n.id === "filter" ? {...n, position:{x:180,y:90}} : n) });
  assert.notEqual(moved.flows[0].path,geometry.flows[0].path);
  assert.deepEqual(moved.flows[1].path,geometry.flows[1].path);
});

test("moving a queue moves its connections and bounded item markers together", () => {
  const original = shiftSchemeGeometry(baseline.scheme);
  const moved = shiftSchemeGeometry({ ...baseline.scheme, nodes: baseline.scheme.nodes.map((n) => n.display === "queue"
    ? {...n,position:{x:n.position!.x+10,y:n.position!.y+5},value:2} : n) });
  assert.deepEqual(moved.queues[0].dots,[{x:105,y:225},{x:127,y:225}]);
  assert.notEqual(moved.flows[1].path,original.flows[1].path);
  assert.notEqual(moved.flows[2].path,original.flows[2].path);
});

test("flow hit targets sit on their actual orthogonal paths", () => {
  const geometry = shiftSchemeGeometry({ nodes:[node("source",25,30),node("target",200,170)],flows:[flow("branch","source","target")] });
  const edge=geometry.flows[0];
  assert.ok(edge.points.slice(1).every((point,index) => point.x===edge.points[index].x || point.y===edge.points[index].y));
  assert.ok(edge.points.slice(1).some((point,index) => {
    const previous=edge.points[index],middle=edge.midpoint;
    return (point.x===previous.x && middle.x===point.x && middle.y>=Math.min(point.y,previous.y) && middle.y<=Math.max(point.y,previous.y)) ||
      (point.y===previous.y && middle.y===point.y && middle.x>=Math.min(point.x,previous.x) && middle.x<=Math.max(point.x,previous.x));
  }));
});

test("unrenderable references and nonfinite geometry cannot produce corrupt SVG or off-canvas nodes", () => {
  const geometry=shiftSchemeGeometry({ nodes:[node("bad",NaN,Infinity),node("outside",999,-100)],
    flows:[flow("valid","bad","outside"),flow("missing","bad","gone"),flow("self","bad","bad")] });
  assert.equal(geometry.flows.length,1);
  assert.ok(!/NaN|Infinity/.test(geometry.flows[0].path));
  assert.ok(geometry.nodes.every((n) => n.x>=0 && n.y>=0 && n.x+n.width<=350 && n.y+n.height<=270));
});
