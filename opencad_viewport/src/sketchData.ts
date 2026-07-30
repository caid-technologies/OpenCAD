import type {
  FeatureNodeView,
  SketchConstraint,
  SketchEntity,
  SketchPayload,
} from "./types";

const SKETCH_OPERATIONS = new Set(["add_sketch", "create_sketch"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function pair(value: unknown): [number, number] | null {
  if (!Array.isArray(value) || value.length !== 2) {
    return null;
  }
  const x = finiteNumber(value[0]);
  const y = finiteNumber(value[1]);
  return x === null || y === null ? null : [x, y];
}

export function isSketchNode(node: FeatureNodeView | null | undefined): boolean {
  if (!node) {
    return false;
  }
  return SKETCH_OPERATIONS.has(node.operation) || node.sketch_id === node.id;
}

function normalizeEntity(key: string, value: unknown): SketchEntity | null {
  if (!isRecord(value) || typeof value.type !== "string") {
    return null;
  }
  const id = typeof value.id === "string" ? value.id : key;

  if (value.type === "point") {
    const x = finiteNumber(value.x);
    const y = finiteNumber(value.y);
    return x === null || y === null ? null : { id, type: "point", x, y };
  }

  if (value.type === "line") {
    const start = pair(value.start);
    const end = pair(value.end);
    const x1 = finiteNumber(value.x1) ?? start?.[0] ?? null;
    const y1 = finiteNumber(value.y1) ?? start?.[1] ?? null;
    const x2 = finiteNumber(value.x2) ?? end?.[0] ?? null;
    const y2 = finiteNumber(value.y2) ?? end?.[1] ?? null;
    return x1 === null || y1 === null || x2 === null || y2 === null
      ? null
      : { id, type: "line", x1, y1, x2, y2 };
  }

  if (value.type === "circle") {
    const center = pair(value.center);
    const cx = finiteNumber(value.cx) ?? finiteNumber(value.x) ?? center?.[0] ?? null;
    const cy = finiteNumber(value.cy) ?? finiteNumber(value.y) ?? center?.[1] ?? null;
    const radius = finiteNumber(value.radius);
    return cx === null || cy === null || radius === null
      ? null
      : { id, type: "circle", cx, cy, radius };
  }

  if (value.type === "arc") {
    const center = pair(value.center);
    const cx = finiteNumber(value.cx) ?? center?.[0] ?? null;
    const cy = finiteNumber(value.cy) ?? center?.[1] ?? null;
    const radius = finiteNumber(value.radius);
    const startAngle = finiteNumber(value.start_angle);
    const endAngle = finiteNumber(value.end_angle);
    return cx === null || cy === null || radius === null || startAngle === null || endAngle === null
      ? null
      : { id, type: "arc", cx, cy, radius, start_angle: startAngle, end_angle: endAngle };
  }

  if (value.type === "rectangle") {
    const x = finiteNumber(value.x);
    const y = finiteNumber(value.y);
    const width = finiteNumber(value.width);
    const height = finiteNumber(value.height);
    return x === null || y === null || width === null || height === null
      ? null
      : { id, type: "rectangle", x, y, width, height };
  }

  return null;
}

function normalizeConstraint(value: unknown): SketchConstraint | null {
  if (!isRecord(value) || typeof value.id !== "string" || typeof value.type !== "string" || typeof value.a !== "string") {
    return null;
  }
  const constraint: SketchConstraint = { id: value.id, type: value.type, a: value.a };
  if (typeof value.b === "string") {
    constraint.b = value.b;
  }
  const numericValue = finiteNumber(value.value);
  if (numericValue !== null) {
    constraint.value = numericValue;
  }
  return constraint;
}

export function sketchFromNode(node: FeatureNodeView | null | undefined): SketchPayload | null {
  if (!node || !isSketchNode(node)) {
    return null;
  }

  const rawEntities = node.parameters.entities;
  if (!isRecord(rawEntities)) {
    return null;
  }

  const entities: Record<string, SketchEntity> = {};
  Object.entries(rawEntities).forEach(([key, value]) => {
    const entity = normalizeEntity(key, value);
    if (entity) {
      entities[key] = { ...entity, id: key } as SketchEntity;
    }
  });

  const rawConstraints = Array.isArray(node.parameters.constraints) ? node.parameters.constraints : [];
  const constraints = rawConstraints
    .map(normalizeConstraint)
    .filter((constraint): constraint is SketchConstraint => constraint !== null);

  return { entities, constraints };
}
