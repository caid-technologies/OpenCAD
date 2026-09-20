import axios from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OpenCadApiClient } from "./client";

vi.mock("axios", () => ({
  default: {
    post: vi.fn(),
    put: vi.fn(),
    get: vi.fn(),
    isAxiosError: vi.fn(),
  },
}));

const mockedAxios = vi.mocked(axios, true);

describe("OpenCadApiClient routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uses backend gateway routes for solver, agent, and tree", async () => {
    mockedAxios.post.mockResolvedValue({ data: { status: "SOLVED", sketch: { entities: {}, constraints: [] } } });
    mockedAxios.get.mockResolvedValue({ data: { nodes: {}, root_id: "root", active_branch: "main", revision: 0 } });

    const client = new OpenCadApiClient("http://127.0.0.1:8003", undefined, false, false);

    await client.solveSketch({ entities: {}, constraints: [] });
    await client.sendChat({
      message: "hi",
      tree_state: { nodes: {}, root_id: "root", active_branch: "main", revision: 0 },
      conversation_history: [],
    });
    await client.getTree("root");

    expect(mockedAxios.post).toHaveBeenNthCalledWith(1, "http://127.0.0.1:8003/solver/sketch/solve", {
      entities: {},
      constraints: [],
    });
    expect(mockedAxios.post).toHaveBeenNthCalledWith(2, "http://127.0.0.1:8003/agent/chat", {
      message: "hi",
      tree_state: { nodes: {}, root_id: "root", active_branch: "main", revision: 0 },
      conversation_history: [],
    });
    expect(mockedAxios.get).toHaveBeenNthCalledWith(1, "http://127.0.0.1:8003/tree/trees/root");
  });

  it("uses /kernel prefixed mesh route by default", async () => {
    mockedAxios.get.mockResolvedValue({ data: { vertices: [0, 0, 0], faces: [0, 0, 0], normals: [0, 1, 0] } });

    const client = new OpenCadApiClient("http://127.0.0.1:8003", undefined, false, false);
    await client.getMesh("shape-1", 0.2);

    expect(mockedAxios.get).toHaveBeenCalledWith("http://127.0.0.1:8003/kernel/shapes/shape-1/mesh", {
      params: { deflection: 0.2 },
    });
  });

  it("uploads STEP, STP, and STL files through the kernel gateway", async () => {
    const result = { shape_id: "shape-imported", filename: "bracket.stl", format: "stl" };
    mockedAxios.post.mockResolvedValue({ data: result });
    const file = new File(["solid bracket"], "bracket.stl", { type: "model/stl" });
    const client = new OpenCadApiClient("http://127.0.0.1:8003", undefined, false, false);

    await expect(client.importCadFile(file)).resolves.toEqual(result);
    expect(mockedAxios.post).toHaveBeenCalledWith(
      "http://127.0.0.1:8003/kernel/files/import",
      file,
      {
        params: { filename: "bracket.stl" },
        headers: { "Content-Type": "application/octet-stream" },
      },
    );
  });

  it("downloads the selected shape in the requested CAD format", async () => {
    const blob = new Blob(["ISO-10303-21"], { type: "model/step" });
    mockedAxios.get.mockResolvedValue({ data: blob });
    const client = new OpenCadApiClient("http://127.0.0.1:8003", undefined, false, false);

    await expect(client.exportCadFile("shape-1", "stp", "Bracket.stp")).resolves.toBe(blob);
    expect(mockedAxios.get).toHaveBeenCalledWith(
      "http://127.0.0.1:8003/kernel/files/shape-1/export",
      {
        params: { format: "stp", filename: "Bracket.stp" },
        responseType: "blob",
      },
    );
  });

  it("registers, updates, and rebuilds a sketch tree", async () => {
    const tree = {
      nodes: {
        "sketch-1": {
          id: "sketch-1",
          name: "Profile",
          operation: "create_sketch",
          parameters: { entities: {}, constraints: [] },
          typed_parameters: {},
          parameter_bindings: [],
          sketch_id: "sketch-1",
          parent_id: null,
          tool_refs: [],
          depends_on: [],
          shape_id: "shape-1",
          status: "built" as const,
          suppressed: false,
        },
      },
      root_id: "sketch-1",
      active_branch: "main",
      revision: 0,
    };
    const sketch = {
      entities: { c1: { id: "c1", type: "circle" as const, cx: 0, cy: 0, radius: 5 } },
      constraints: [],
    };
    mockedAxios.post.mockResolvedValueOnce({ data: tree }).mockResolvedValueOnce({ data: tree });
    mockedAxios.put.mockResolvedValue({ data: tree });

    const client = new OpenCadApiClient("http://127.0.0.1:8003", undefined, false, false);
    await client.updateSketch(tree, "sketch-1", sketch);

    expect(mockedAxios.post).toHaveBeenNthCalledWith(1, "http://127.0.0.1:8003/tree/trees", tree);
    expect(mockedAxios.put).toHaveBeenCalledWith(
      "http://127.0.0.1:8003/tree/trees/sketch-1/nodes/sketch-1/sketch",
      sketch,
    );
    expect(mockedAxios.post).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8003/tree/trees/sketch-1/rebuild",
      { continue_on_error: false },
    );
  });

  it("surfaces agent API error details", async () => {
    const error = { response: { data: { detail: "Chat requires an LLM." } } };
    mockedAxios.post.mockRejectedValue(error);
    mockedAxios.isAxiosError.mockReturnValue(true);

    const client = new OpenCadApiClient("http://127.0.0.1:8003", undefined, false, false);

    await expect(client.sendChat({
      message: "Build a cog",
      tree_state: { nodes: {}, root_id: "root", active_branch: "main", revision: 0 },
      conversation_history: [],
    })).rejects.toThrow("Chat requires an LLM.");
  });


  it("creates and evaluates kinematic joints through kernel operations", async () => {
    const joint = {
      id: "joint-1",
      type: "revolute" as const,
      parent_shape_id: "base",
      child_shape_id: "lid",
      axis: [0, 0, 1] as [number, number, number],
      origin_mm: [10, 0, 0] as [number, number, number],
      lower_limit: 0,
      upper_limit: Math.PI / 2,
      unit: "radian" as const,
      metadata: {},
    };
    const pose = {
      joint_id: "joint-1",
      child_shape_id: "lid",
      progress: 1,
      value: Math.PI / 2,
      unit: "radian" as const,
      transform: {
        translation_mm: [10, -10, 0] as [number, number, number],
        rotation_quaternion_xyzw: [0, 0, Math.SQRT1_2, Math.SQRT1_2] as [number, number, number, number],
      },
    };
    mockedAxios.post
      .mockResolvedValueOnce({ data: { ok: true, metadata: { joint } } })
      .mockResolvedValueOnce({ data: { ok: true, metadata: { pose } } });

    const client = new OpenCadApiClient("http://127.0.0.1:8003", undefined, false, false);

    await expect(client.createKinematicJoint({
      type: "revolute",
      parent_shape_id: "base",
      child_shape_id: "lid",
      axis: [0, 0, 1],
      origin_mm: [10, 0, 0],
      lower_limit: 0,
      upper_limit: Math.PI / 2,
    })).resolves.toEqual(joint);
    await expect(client.evaluateKinematicJoint("joint-1", 1)).resolves.toEqual(pose);

    expect(mockedAxios.post).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8003/kernel/operations/create_kinematic_joint",
      {
        payload: {
          type: "revolute",
          parent_shape_id: "base",
          child_shape_id: "lid",
          axis: [0, 0, 1],
          origin_mm: [10, 0, 0],
          lower_limit: 0,
          upper_limit: Math.PI / 2,
        },
      },
    );
    expect(mockedAxios.post).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8003/kernel/operations/evaluate_kinematic_joint",
      { payload: { joint_id: "joint-1", progress: 1 } },
    );
  });

  it("returns evaluated assembly transforms keyed by child shape", async () => {
    const transforms = {
      lid: {
        translation_mm: [10, -10, 0],
        rotation_quaternion_xyzw: [0, 0, Math.SQRT1_2, Math.SQRT1_2],
      },
    };
    mockedAxios.post.mockResolvedValue({
      data: { ok: true, metadata: { transforms } },
    });
    const client = new OpenCadApiClient("http://127.0.0.1:8003", undefined, false, false);

    await expect(
      client.evaluateKinematicAssembly({ "joint-1": 1 }),
    ).resolves.toEqual(transforms);

    expect(mockedAxios.post).toHaveBeenCalledWith(
      "http://127.0.0.1:8003/kernel/operations/evaluate_kinematic_assembly",
      { payload: { progress_by_joint: { "joint-1": 1 } } },
    );
  });

  it("uses custom kernel URL for streaming mesh events", () => {
    const close = vi.fn();
    let capturedUrl = "";

    class FakeEventSource {
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onerror: (() => void) | null = null;

      constructor(url: string) {
        capturedUrl = url;
      }

      close(): void {
        close();
      }
    }

    vi.stubGlobal("EventSource", FakeEventSource);

    const client = new OpenCadApiClient("http://127.0.0.1:8003", "http://127.0.0.1:8000", false, false);
    client.streamMesh("shape-2", vi.fn(), { deflection: 0.4 });

    expect(capturedUrl).toBe("http://127.0.0.1:8000/shapes/shape-2/mesh/stream?deflection=0.4");
  });
});
