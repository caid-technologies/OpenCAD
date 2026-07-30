import { useState } from "react";
import type { ChatHistoryItem, ChatOperationExecution, ChatRequestPayload } from "../types";

interface ChatPanelProps {
  onSend: (request: Omit<ChatRequestPayload, "tree_state">) => Promise<{
    response: string;
    operations: ChatOperationExecution[];
  }>;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function ChatPanel({ onSend }: ChatPanelProps): JSX.Element {
  const [messages, setMessages] = useState<ChatHistoryItem[]>([]);
  const [operations, setOperations] = useState<ChatOperationExecution[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);

  const submit = async () => {
    const message = input.trim();
    if (!message || pending) {
      return;
    }

    setPending(true);
    setInput("");
    const priorHistory = messages;
    setMessages([...priorHistory, { role: "user", content: message } satisfies ChatHistoryItem]);
    setOperations([]);

    try {
      const result = await onSend({
        message,
        conversation_history: priorHistory,
      });

      const assistantMessage: ChatHistoryItem = { role: "assistant", content: "" };
      setMessages((current) => [...current, assistantMessage]);

      let stream = "";
      for (const ch of result.response) {
        stream += ch;
        setMessages((current) => {
          const next = [...current];
          next[next.length - 1] = { role: "assistant", content: stream };
          return next;
        });
        await sleep(9);
      }

      const shown: ChatOperationExecution[] = [];
      for (const operation of result.operations) {
        shown.push(operation);
        setOperations([...shown]);
        await sleep(170);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to reach the OpenCAD agent.";
      setMessages((current) => [...current, { role: "assistant", content: message }]);
    } finally {
      setPending(false);
    }
  };

  return (
    <section className="chat-panel">
      <header className="chat-header">
        <h3>AI Chat</h3>
      </header>

      <div className="chat-messages">
        {messages.map((message, index) => (
          <div key={`${message.role}-${index}`} className={`chat-message ${message.role}`}>
            <strong>{message.role === "user" ? "You" : message.role === "assistant" ? "Agent" : "System"}</strong>
            <p>{message.content}</p>
          </div>
        ))}
      </div>

      <div className="chat-ops">
        {operations.map((operation, index) => (
          <div key={`${operation.tool}-${index}`} className="chat-op-row">
            <span className={`op-status ${operation.status}`}>{operation.status}</span>
            <span className="op-tool">{operation.tool}</span>
            <code>{JSON.stringify(operation.arguments)}</code>
          </div>
        ))}
      </div>

      <div className="chat-input-row">
        <input
          type="text"
          value={input}
          placeholder="Describe a part to build"
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              void submit();
            }
          }}
        />
        <button type="button" onClick={() => void submit()} disabled={pending}>
          {pending ? "Running..." : "Send"}
        </button>
      </div>
    </section>
  );
}
