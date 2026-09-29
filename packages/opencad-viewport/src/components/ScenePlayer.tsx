import { useEffect, useMemo, useState } from "react";
import type { MeshPayload } from "../types";
import { createScenePlayer, sceneDuration } from "../scene";
import type { SceneDocument } from "../scene";
import { clampSceneTime, validateSceneMotion } from "../sceneCollision";
import { Viewport3D } from "./Viewport3D";

export interface ScenePlayerProps {
  document: SceneDocument;
  meshes: MeshPayload[];
  onSave?: (document: SceneDocument) => void;
}

/** A local, deterministic interaction player. Meshes stay independent roots. */
export function ScenePlayer({
  document,
  meshes,
  onSave,
}: ScenePlayerProps): JSX.Element {
  const sample = useMemo(() => createScenePlayer(document), [document]);
  const duration = sceneDuration(document);
  const check = useMemo(() => validateSceneMotion(document), [document]);
  const blocked = check.status === "collision" || check.status === "uncertain";
  const limit = blocked ? check.safe_time_s : duration;
  const [time, setTime] = useState(
    clampSceneTime(document.time_s, check, duration),
  );
  const [playing, setPlaying] = useState(false);
  // Clamp during render as well: a newly supplied document must never display
  // the previous document's cursor past its limit before the reset effect runs.
  const currentTime = clampSceneTime(time, check, duration);
  useEffect(() => {
    setTime(clampSceneTime(document.time_s, check, duration));
    setPlaying(false);
  }, [document, duration, check]);
  useEffect(() => {
    if (!playing) return;
    let frame: number;
    let previous: number | undefined;
    const tick = (now: number) => {
      const delta = previous === undefined ? 0 : (now - previous) / 1000;
      previous = now;
      setTime((value) => clampSceneTime(value + delta, check, duration));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [duration, playing, check]);
  useEffect(() => {
    if (currentTime >= limit) setPlaying(false);
  }, [limit, currentTime]);
  const state = useMemo(() => sample(currentTime), [sample, currentTime]);
  const currentAction = document.interactions.find(
    (action) => state.interaction_states[action.id] === "active",
  );
  const held = Object.values(state.attachments);
  const highlighted = new Set(
    held.flatMap((item) =>
      Object.values(
        document.entities[item.target_id].assembly.components,
      ).flatMap((component) => component.geometry_refs),
    ),
  );

  return (
    <section className="scene-player" aria-label={document.name}>
      <div className="scene-controls">
        <strong>{document.name}</strong>
        <button
          type="button"
          disabled={duration === 0 || (blocked && currentTime >= limit)}
          onClick={() => {
            if (currentTime >= duration) setTime(0);
            setPlaying((value) => !value);
          }}
        >
          {playing ? "Pause" : "Play"}
        </button>
        <button
          type="button"
          onClick={() => {
            setPlaying(false);
            setTime(0);
          }}
        >
          Reset
        </button>
        <label className="scene-timeline">
          Timeline
          <input
            aria-label="Scene time"
            type="range"
            min={0}
            max={duration}
            step={0.01}
            value={currentTime}
            onChange={(event) => {
              setPlaying(false);
              setTime(
                clampSceneTime(Number(event.target.value), check, duration),
              );
            }}
          />
        </label>
        <output aria-label="Playback time">
          {currentTime.toFixed(1)} / {duration.toFixed(1)} s
        </output>
        {onSave && (
          <button
            type="button"
            onClick={() => onSave({ ...document, time_s: currentTime })}
          >
            Save scene
          </button>
        )}
      </div>
      {blocked && (
        <div className="scene-collision" role="alert">
          {check.status === "collision"
            ? "Collision detected"
            : "Motion could not be verified"}
          : {check.collider_ids.join(" / ")} near {check.time_s.toFixed(3)} s.{" "}
          Playback and seeking stop at {limit.toFixed(3)} s.
        </div>
      )}
      <div className="scene-status" role="status">
        {check.status === "clear"
          ? "Collision check passed · "
          : check.status === "unchecked"
            ? "Some geometry has no collision coverage · "
            : ""}
        {currentAction?.id ?? "Sequence complete"}
        {held.length > 0
          ? ` · Holding ${held.map((item) => document.entities[item.target_id].name).join(", ")}`
          : " · Gripper free"}
        {Object.entries(state.placements).map(
          ([target, destination]) =>
            ` · ${document.entities[target].name} placed on ${document.entities[destination].name}`,
        )}
      </div>
      <Viewport3D
        meshes={meshes}
        shapeTransforms={state.shape_transforms}
        highlightedShapeIds={highlighted}
        collisionShapeIds={
          blocked && currentTime >= limit ? new Set(check.shape_ids) : undefined
        }
        collisionColor={check.status === "uncertain" ? "#d97706" : "#dc2626"}
      />
    </section>
  );
}
