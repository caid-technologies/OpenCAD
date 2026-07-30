import axios from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OpenCadApiClient } from "./client";

vi.mock("axios", () => ({
  default: {
    post: vi.fn(),
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

  it("surfaces an unsupported-prompt detail from the agent API", async () => {
    const error = { response: { data: { detail: "Unsupported CAD request." } } };
    mockedAxios.post.mockRejectedValue(error);
    mockedAxios.isAxiosError.mockReturnValue(true);

    const client = new OpenCadApiClient("http://127.0.0.1:8003", undefined, false, false);

    await expect(client.sendChat({
      message: "Build a cog",
      tree_state: { nodes: {}, root_id: "root", active_branch: "main", revision: 0 },
      conversation_history: [],
      generate_code: true,
    })).rejects.toThrow("Unsupported CAD request.");
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
