import axios from "axios";
import { mockChat, mockSolveSketch } from "../mock/mockData";
import type {
  ChatRequestPayload,
  ChatResponsePayload,
  FeatureTreeView,
  MeshPayload,
  SketchPayload,
  SolverResult,
} from "../types";

/** A single SSE mesh chunk from the kernel streaming endpoint. */
export interface MeshStreamChunk {
  vertices: number[];
  faces: number[];
  normals: number[];
  faceIndex: number;
  totalFaces: number;
  done: boolean;
  error?: string;
}

export class OpenCadApiClient {
  private readonly baseUrl: string;
  private readonly kernelUrl: string;
  private readonly useMock: boolean;
  private readonly useChatMock: boolean;

  constructor(
    baseUrl = import.meta.env.VITE_BASE_URL ?? "http://127.0.0.1:8000",
    kernelUrl?: string,
    useMock = import.meta.env.VITE_USE_MOCK !== "false",
    useChatMock = import.meta.env.VITE_USE_CHAT_MOCK === "true",
  ) {
    this.baseUrl = baseUrl;
    this.kernelUrl = kernelUrl ?? `${baseUrl}/kernel`;
    this.useMock = useMock;
    this.useChatMock = useChatMock;
  }

  async solveSketch(sketch: SketchPayload): Promise<SolverResult> {
    if (this.useMock) {
      return mockSolveSketch(sketch);
    }
    const response = await axios.post<SolverResult>(`${this.baseUrl}/solver/sketch/solve`, sketch);
    return response.data;
  }

  async sendChat(request: ChatRequestPayload): Promise<ChatResponsePayload> {
    if (this.useChatMock) {
      const mock = await mockChat(request.message, Boolean(request.reasoning));
      return {
        response: mock.response,
        operations_executed: mock.operations,
        new_tree_state: request.tree_state
      };
    }

    try {
      const response = await axios.post<ChatResponsePayload>(`${this.baseUrl}/agent/chat`, request);
      return response.data;
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const detail = error.response?.data?.detail;
        if (typeof detail === "string") {
          throw new Error(detail);
        }
      }
      throw error;
    }
  }

  async getTree(treeId: string): Promise<FeatureTreeView> {
    const response = await axios.get<FeatureTreeView>(`${this.baseUrl}/tree/trees/${treeId}`);
    return response.data;
  }

  async getMesh(shapeId: string, deflection = 0.1): Promise<MeshPayload> {
    const response = await axios.get<MeshPayload>(
      `${this.kernelUrl}/shapes/${shapeId}/mesh`,
      { params: { deflection } },
    );
    return { ...response.data, shapeId };
  }

  /**
   * Stream mesh data face-by-face via Server-Sent Events.
   *
   * Each chunk contains triangulation data for one topological face.
   * The caller receives progressive updates and can render incrementally.
   */
  streamMesh(
    shapeId: string,
    onChunk: (chunk: MeshStreamChunk) => void,
    options: { deflection?: number; signal?: AbortSignal } = {},
  ): void {
    const { deflection = 0.1, signal } = options;
    const url = `${this.kernelUrl}/shapes/${shapeId}/mesh/stream?deflection=${deflection}`;

    const eventSource = new EventSource(url);

    if (signal) {
      signal.addEventListener("abort", () => eventSource.close());
    }

    eventSource.onmessage = (event) => {
      try {
        const chunk: MeshStreamChunk = JSON.parse(event.data);
        onChunk(chunk);
        if (chunk.done || chunk.error) {
          eventSource.close();
        }
      } catch {
        eventSource.close();
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
    };
  }
}
