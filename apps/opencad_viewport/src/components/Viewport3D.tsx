import { GizmoHelper, GizmoViewport, OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BufferAttribute, BufferGeometry, EdgesGeometry } from "three";
import type { MeshPayload } from "../types";
import type { MeshStreamChunk, OpenCadApiClient } from "../api/client";

interface Viewport3DProps {
  meshes: MeshPayload[];
  selectedShapeId?: string | null;
  onSelectShape?: (shapeId: string) => void;
  /** Optional: provide the API client to enable SSE streaming. */
  apiClient?: OpenCadApiClient;
  /** When true, prefer SSE streaming over static meshes. */
  useStreaming?: boolean;
}

function toFloat32(values: number[] | Float32Array | undefined): Float32Array {
  if (!values) {
    return new Float32Array();
  }
  return values instanceof Float32Array ? values : new Float32Array(values);
}

function toUint32(values: number[] | Uint32Array): Uint32Array {
  return values instanceof Uint32Array ? values : new Uint32Array(values);
}

function MeshItem({
  mesh,
  selected,
  onSelect
}: {
  mesh: MeshPayload;
  selected: boolean;
  onSelect?: (shapeId: string) => void;
}): JSX.Element {
  const [hovered, setHovered] = useState(false);
  const geometry = useMemo(() => {
    const g = new BufferGeometry();
    const positions = toFloat32(mesh.vertices);
    const indices = toUint32(mesh.faces);
    const normals = toFloat32(mesh.normals);

    g.setAttribute("position", new BufferAttribute(positions, 3));
    g.setIndex(new BufferAttribute(indices, 1));
    if (normals.length === positions.length) {
      g.setAttribute("normal", new BufferAttribute(normals, 3));
    } else {
      g.computeVertexNormals();
    }
    return g;
  }, [mesh.faces, mesh.normals, mesh.vertices]);

  const edgeGeometry = useMemo(() => new EdgesGeometry(geometry), [geometry]);

  useEffect(() => {
    return () => {
      geometry.dispose();
      edgeGeometry.dispose();
    };
  }, [edgeGeometry, geometry]);

  const color = selected ? "#1f6feb" : hovered ? "#8aa2bf" : "#9ca3af";

  return (
    <group>
      <mesh
        geometry={geometry}
        onPointerOver={(event) => {
          event.stopPropagation();
          setHovered(true);
        }}
        onPointerOut={(event) => {
          event.stopPropagation();
          setHovered(false);
        }}
        onPointerDown={(event) => {
          event.stopPropagation();
          onSelect?.(mesh.shapeId);
        }}
      >
        <meshStandardMaterial color={color} flatShading metalness={0.1} roughness={0.75} />
      </mesh>
      <lineSegments geometry={edgeGeometry}>
        <lineBasicMaterial color={selected ? "#0b4ea2" : "#5f6774"} />
      </lineSegments>
    </group>
  );
}

/**
 * StreamingMeshItem — renders a mesh that builds up progressively
 * as SSE chunks arrive from the kernel.
 */
function StreamingMeshItem({
  shapeId,
  apiClient,
  selected,
  onSelect,
}: {
  shapeId: string;
  apiClient: OpenCadApiClient;
  selected: boolean;
  onSelect?: (shapeId: string) => void;
}): JSX.Element | null {
  const [hovered, setHovered] = useState(false);
  const geometryRef = useRef<BufferGeometry | null>(null);
  const edgeGeomRef = useRef<EdgesGeometry | null>(null);
  const [, forceUpdate] = useState(0);

  // Accumulate chunks into flat arrays
  const accum = useRef<{ verts: number[]; faces: number[]; norms: number[] }>({
    verts: [],
    faces: [],
    norms: [],
  });

  useEffect(() => {
    accum.current = { verts: [], faces: [], norms: [] };
    const controller = new AbortController();

    apiClient.streamMesh(
      shapeId,
      (chunk: MeshStreamChunk) => {
        if (chunk.error) return;

        const vertOffset = accum.current.verts.length / 3;
        accum.current.verts.push(...chunk.vertices);
        accum.current.norms.push(...chunk.normals);
        // Offset face indices by the current vertex count
        for (const idx of chunk.faces) {
          accum.current.faces.push(idx + vertOffset);
        }

        // Rebuild geometry
        const g = new BufferGeometry();
        const positions = new Float32Array(accum.current.verts);
        const indices = new Uint32Array(accum.current.faces);
        const normals = new Float32Array(accum.current.norms);

        g.setAttribute("position", new BufferAttribute(positions, 3));
        g.setIndex(new BufferAttribute(indices, 1));
        if (normals.length === positions.length) {
          g.setAttribute("normal", new BufferAttribute(normals, 3));
        } else {
          g.computeVertexNormals();
        }
        g.computeBoundingSphere();

        // Dispose old
        geometryRef.current?.dispose();
        edgeGeomRef.current?.dispose();
        geometryRef.current = g;
        edgeGeomRef.current = new EdgesGeometry(g);
        forceUpdate((n) => n + 1);
      },
      { signal: controller.signal },
    );

    return () => {
      controller.abort();
      geometryRef.current?.dispose();
      edgeGeomRef.current?.dispose();
    };
  }, [shapeId, apiClient]);

  if (!geometryRef.current) return null;

  const color = selected ? "#1f6feb" : hovered ? "#8aa2bf" : "#9ca3af";

  return (
    <group>
      <mesh
        geometry={geometryRef.current}
        onPointerOver={(event) => { event.stopPropagation(); setHovered(true); }}
        onPointerOut={(event) => { event.stopPropagation(); setHovered(false); }}
        onPointerDown={(event) => { event.stopPropagation(); onSelect?.(shapeId); }}
      >
        <meshStandardMaterial color={color} flatShading metalness={0.1} roughness={0.75} />
      </mesh>
      {edgeGeomRef.current && (
        <lineSegments geometry={edgeGeomRef.current}>
          <lineBasicMaterial color={selected ? "#0b4ea2" : "#5f6774"} />
        </lineSegments>
      )}
    </group>
  );
}

export function Viewport3D({ meshes, selectedShapeId, onSelectShape, apiClient, useStreaming }: Viewport3DProps): JSX.Element {
  // Collect unique shape IDs for streaming mode
  const streamShapeIds = useMemo(() => {
    if (!useStreaming || !apiClient) return [];
    return meshes.map((m) => m.shapeId);
  }, [meshes, useStreaming, apiClient]);

  return (
    <div className="viewport3d">
      <Canvas camera={{ position: [45, -55, 30], up: [0, 0, 1], fov: 45 }}>
        <color attach="background" args={["#f5f7fb"]} />
        <ambientLight intensity={0.8} />
        <directionalLight position={[40, -30, 50]} intensity={1.1} />
        <gridHelper args={[140, 28, "#8f98a8", "#ced3db"]} rotation={[Math.PI / 2, 0, 0]} />

        {useStreaming && apiClient
          ? streamShapeIds.map((id) => (
              <StreamingMeshItem
                key={id}
                shapeId={id}
                apiClient={apiClient}
                selected={id === selectedShapeId}
                onSelect={onSelectShape}
              />
            ))
          : meshes.map((mesh) => (
              <MeshItem
                key={mesh.shapeId}
                mesh={mesh}
                selected={mesh.shapeId === selectedShapeId}
                onSelect={onSelectShape}
              />
            ))}

        <OrbitControls makeDefault />
        <GizmoHelper alignment="bottom-right" margin={[72, 72]}>
          <GizmoViewport axisColors={["#d14343", "#0f8f53", "#2e63cc"]} labelColor="#18212f" />
        </GizmoHelper>
      </Canvas>
    </div>
  );
}
