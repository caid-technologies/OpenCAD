import { useEffect, useMemo, useState } from "react";
import type { SketchConstraint, SketchEntity, SketchPayload, SolverResult } from "../types";

interface SketchEditorProps {
  active: boolean;
  name: string;
  sketch: SketchPayload | null;
  solveSketch: (sketch: SketchPayload) => Promise<SolverResult>;
  onApply: (sketch: SketchPayload) => Promise<void>;
}

interface EntityField {
  key: string;
  label: string;
  value: number;
}

function iconForConstraint(type: string): string {
  const icons: Record<string, string> = {
    horizontal: "H",
    vertical: "V",
    parallel: "||",
    perpendicular: "⊥",
    coincident: "C",
    distance: "D",
    angle: "∠",
    equal: "=",
    fixed: "F",
    tangent: "T",
  };
  return icons[type] ?? "*";
}

function fieldsForEntity(entity: SketchEntity): EntityField[] {
  if (entity.type === "point") {
    return [{ key: "x", label: "X", value: entity.x }, { key: "y", label: "Y", value: entity.y }];
  }
  if (entity.type === "line") {
    return [
      { key: "x1", label: "X1", value: entity.x1 },
      { key: "y1", label: "Y1", value: entity.y1 },
      { key: "x2", label: "X2", value: entity.x2 },
      { key: "y2", label: "Y2", value: entity.y2 },
    ];
  }
  if (entity.type === "circle") {
    return [
      { key: "cx", label: "CX", value: entity.cx },
      { key: "cy", label: "CY", value: entity.cy },
      { key: "radius", label: "R", value: entity.radius },
    ];
  }
  if (entity.type === "arc") {
    return [
      { key: "cx", label: "CX", value: entity.cx },
      { key: "cy", label: "CY", value: entity.cy },
      { key: "radius", label: "R", value: entity.radius },
      { key: "start_angle", label: "A1", value: entity.start_angle },
      { key: "end_angle", label: "A2", value: entity.end_angle },
    ];
  }
  return [
    { key: "x", label: "X", value: entity.x },
    { key: "y", label: "Y", value: entity.y },
    { key: "width", label: "W", value: entity.width },
    { key: "height", label: "H", value: entity.height },
  ];
}

function withField(entity: SketchEntity, field: string, value: number): SketchEntity {
  const positiveValue = Math.max(0.000001, Math.abs(value));
  if (entity.type === "point") {
    return field === "x" ? { ...entity, x: value } : { ...entity, y: value };
  }
  if (entity.type === "line") {
    if (field === "x1") return { ...entity, x1: value };
    if (field === "y1") return { ...entity, y1: value };
    if (field === "x2") return { ...entity, x2: value };
    return { ...entity, y2: value };
  }
  if (entity.type === "circle") {
    if (field === "cx") return { ...entity, cx: value };
    if (field === "cy") return { ...entity, cy: value };
    return { ...entity, radius: positiveValue };
  }
  if (entity.type === "arc") {
    if (field === "cx") return { ...entity, cx: value };
    if (field === "cy") return { ...entity, cy: value };
    if (field === "radius") return { ...entity, radius: positiveValue };
    if (field === "start_angle") return { ...entity, start_angle: value };
    return { ...entity, end_angle: value };
  }
  if (field === "x") return { ...entity, x: value };
  if (field === "y") return { ...entity, y: value };
  if (field === "width") return { ...entity, width: positiveValue };
  return { ...entity, height: positiveValue };
}

function updateEntity(sketch: SketchPayload, entityId: string, field: string, value: number): SketchPayload {
  const target = sketch.entities[entityId];
  if (!target) {
    return sketch;
  }

  let oldPoint: [number, number] | null = null;
  let newPoint: [number, number] | null = null;
  if (target.type === "line" && ["x1", "y1", "x2", "y2"].includes(field)) {
    const firstEndpoint = field.endsWith("1");
    oldPoint = firstEndpoint ? [target.x1, target.y1] : [target.x2, target.y2];
    newPoint = [...oldPoint];
    newPoint[field.startsWith("x") ? 0 : 1] = value;
  }

  const entities = Object.fromEntries(
    Object.entries(sketch.entities).map(([id, entity]) => {
      if (oldPoint && newPoint && entity.type === "line") {
        let updated = entity;
        if (entity.x1 === oldPoint[0] && entity.y1 === oldPoint[1]) {
          updated = { ...updated, x1: newPoint[0], y1: newPoint[1] };
        }
        if (entity.x2 === oldPoint[0] && entity.y2 === oldPoint[1]) {
          updated = { ...updated, x2: newPoint[0], y2: newPoint[1] };
        }
        return [id, updated];
      }
      return [id, id === entityId ? withField(entity, field, value) : entity];
    }),
  );
  return { ...sketch, entities };
}

function entityBounds(entities: SketchEntity[]): [number, number, number, number] {
  const xs: number[] = [];
  const ys: number[] = [];
  entities.forEach((entity) => {
    if (entity.type === "point") {
      xs.push(entity.x); ys.push(entity.y);
    } else if (entity.type === "line") {
      xs.push(entity.x1, entity.x2); ys.push(entity.y1, entity.y2);
    } else if (entity.type === "circle" || entity.type === "arc") {
      xs.push(entity.cx - entity.radius, entity.cx + entity.radius);
      ys.push(entity.cy - entity.radius, entity.cy + entity.radius);
    } else {
      xs.push(entity.x, entity.x + entity.width); ys.push(entity.y, entity.y + entity.height);
    }
  });
  if (xs.length === 0) {
    return [-1, 1, -1, 1];
  }
  return [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
}

function constraintAnchor(entity: SketchEntity): [number, number] {
  if (entity.type === "point") return [entity.x, entity.y];
  if (entity.type === "line") return [(entity.x1 + entity.x2) / 2, (entity.y1 + entity.y2) / 2];
  if (entity.type === "circle" || entity.type === "arc") return [entity.cx, entity.cy];
  return [entity.x + entity.width / 2, entity.y + entity.height / 2];
}

export function SketchEditor({ active, name, sketch, solveSketch, onApply }: SketchEditorProps): JSX.Element | null {
  const [localSketch, setLocalSketch] = useState<SketchPayload | null>(sketch);
  const [solvedSketch, setSolvedSketch] = useState<SketchPayload | null>(null);
  const [solveMessage, setSolveMessage] = useState("Checking sketch…");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    setLocalSketch(sketch);
    setSolvedSketch(null);
    setDirty(false);
    setSaveError(null);
  }, [sketch]);

  useEffect(() => {
    if (!active || !localSketch) {
      return;
    }
    let cancelled = false;
    setSolveMessage("Checking sketch…");
    const timer = window.setTimeout(async () => {
      try {
        const result = await solveSketch(localSketch);
        if (!cancelled) {
          setSolvedSketch(result.status === "OVERCONSTRAINED" ? null : result.sketch);
          setSolveMessage(`${result.status}: ${result.message ?? ""}`.trim());
        }
      } catch (error) {
        if (!cancelled) {
          setSolvedSketch(null);
          setSolveMessage(error instanceof Error ? `Solver error: ${error.message}` : "Solver error");
        }
      }
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [active, localSketch, solveSketch]);

  const constraintRows = useMemo<SketchConstraint[]>(() => localSketch?.constraints ?? [], [localSketch]);
  const entities = useMemo(() => Object.values(localSketch?.entities ?? {}), [localSketch]);
  const transform = useMemo(() => {
    const [minX, maxX, minY, maxY] = entityBounds(entities);
    const width = Math.max(maxX - minX, 1);
    const height = Math.max(maxY - minY, 1);
    const scale = Math.min(280 / width, 190 / height);
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    return {
      x: (value: number) => 160 + (value - centerX) * scale,
      y: (value: number) => 120 - (value - centerY) * scale,
      scale,
    };
  }, [entities]);

  if (!active || !localSketch) {
    return null;
  }

  const changeDraft = (updated: SketchPayload) => {
    setLocalSketch(updated);
    setSolvedSketch(null);
    setDirty(true);
    setSaveError(null);
  };

  return (
    <div className="sketch-overlay">
      <div className="sketch-header">
        <div><strong>Sketch Editor</strong><span className="sketch-name">{name}</span></div>
        <span className="sketch-solver-status">{solveMessage}</span>
      </div>
      <svg viewBox="0 0 320 240" className="sketch-canvas" aria-label={`${name} sketch geometry`}>
        {entities.length === 0 ? <text x="160" y="120" textAnchor="middle" className="sketch-empty">No sketch geometry</text> : null}
        {entities.map((entity) => {
          if (entity.type === "line") {
            return <line key={entity.id} x1={transform.x(entity.x1)} y1={transform.y(entity.y1)} x2={transform.x(entity.x2)} y2={transform.y(entity.y2)} className="sketch-geometry" />;
          }
          if (entity.type === "circle") {
            return <circle key={entity.id} cx={transform.x(entity.cx)} cy={transform.y(entity.cy)} r={entity.radius * transform.scale} className="sketch-geometry" />;
          }
          if (entity.type === "arc") {
            const startX = transform.x(entity.cx + entity.radius * Math.cos(entity.start_angle));
            const startY = transform.y(entity.cy + entity.radius * Math.sin(entity.start_angle));
            const endX = transform.x(entity.cx + entity.radius * Math.cos(entity.end_angle));
            const endY = transform.y(entity.cy + entity.radius * Math.sin(entity.end_angle));
            const largeArc = Math.abs(entity.end_angle - entity.start_angle) > Math.PI ? 1 : 0;
            return <path key={entity.id} d={`M ${startX} ${startY} A ${entity.radius * transform.scale} ${entity.radius * transform.scale} 0 ${largeArc} 0 ${endX} ${endY}`} className="sketch-geometry" />;
          }
          if (entity.type === "rectangle") {
            return <rect key={entity.id} x={transform.x(entity.x)} y={transform.y(entity.y + entity.height)} width={entity.width * transform.scale} height={entity.height * transform.scale} className="sketch-geometry" />;
          }
          return <circle key={entity.id} cx={transform.x(entity.x)} cy={transform.y(entity.y)} r={3} className="sketch-point" />;
        })}
        {localSketch.constraints.map((constraint) => {
          const anchor = localSketch.entities[constraint.a];
          if (!anchor) return null;
          const [x, y] = constraintAnchor(anchor);
          return <text key={constraint.id} x={transform.x(x) + 5} y={transform.y(y) - 5} className="constraint-icon">{iconForConstraint(constraint.type)}</text>;
        })}
      </svg>

      <div className="sketch-section-title">Geometry</div>
      <div className="entity-grid">
        {entities.map((entity) => (
          <div key={entity.id} className="entity-row">
            <span title={entity.id}>{entity.type}</span>
            <div className="entity-fields">
              {fieldsForEntity(entity).map((field) => (
                <label key={field.key}>
                  <span>{field.label}</span>
                  <input type="number" step="any" value={field.value} onChange={(event) => {
                    const value = Number(event.target.value);
                    if (Number.isFinite(value)) changeDraft(updateEntity(localSketch, entity.id, field.key, value));
                  }} />
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="sketch-section-title">Constraints</div>
      <div className="constraint-grid">
        {constraintRows.length === 0 ? <span className="sketch-empty-row">No constraints</span> : null}
        {constraintRows.map((constraint) => (
          <label key={constraint.id} className="constraint-row">
            <span>{constraint.id}</span><span>{constraint.type}</span>
            <input type="number" step="any" value={constraint.value ?? 0} disabled={constraint.value === undefined} onChange={(event) => {
              if (constraint.value === undefined) return;
              const nextValue = Number(event.target.value);
              if (!Number.isFinite(nextValue)) return;
              changeDraft({
                ...localSketch,
                constraints: localSketch.constraints.map((item) => item.id === constraint.id ? { ...item, value: nextValue } : item),
              });
            }} />
          </label>
        ))}
      </div>

      <div className="sketch-actions">
        {saveError ? <span className="sketch-save-error">{saveError}</span> : <span />}
        <button type="button" disabled={!dirty || saving || !solvedSketch} onClick={async () => {
          if (!solvedSketch) return;
          setSaving(true);
          setSaveError(null);
          try {
            await onApply(solvedSketch);
            setLocalSketch(solvedSketch);
            setDirty(false);
          } catch (error) {
            setSaveError(error instanceof Error ? error.message : "Sketch rebuild failed.");
          } finally {
            setSaving(false);
          }
        }}>{saving ? "Rebuilding…" : "Apply & rebuild"}</button>
      </div>
    </div>
  );
}
