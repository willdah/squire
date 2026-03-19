"use client";

/* eslint-disable @next/next/no-img-element */
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { apiGet, apiPost } from "@/lib/api";
import { useWebSocket } from "@/hooks/use-websocket";
import { MessageList, type ChatMessage, type AgentState } from "@/components/chat/message-list";
import { ChatInput, type ChatInputHandle } from "@/components/chat/chat-input";
import { ApprovalDialog } from "@/components/chat/approval-dialog";
import type { MessageInfo, WsApprovalRequest } from "@/lib/types";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { SquarePen } from "lucide-react";

const SESSION_KEY = "squire_chat_session";

const suggestions = [
  "Show system status",
  "Check containers",
  "List alerts",
];

export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-full">
          <Skeleton className="h-8 w-48" />
        </div>
      }
    >
      <ChatPageInner />
    </Suspense>
  );
}

function ConnectionDot({ status }: { status: string }) {
  const color =
    status === "connected"
      ? "bg-gauge-ok"
      : status === "connecting"
        ? "bg-gauge-warn"
        : "bg-gauge-crit";
  const label =
    status === "connected"
      ? "Connected"
      : status === "connecting"
        ? "Connecting"
        : "Disconnected";

  return (
    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className={`inline-block h-2 w-2 rounded-full ${color}`} />
      {label}
    </span>
  );
}

function WelcomeState({ onSuggestion }: { onSuggestion: (text: string) => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 px-4 animate-fade-in">
      <div className="h-16 w-16 rounded-full overflow-hidden bg-muted">
        <img
          src="/squire-avatar.png"
          alt="Squire"
          className="h-full w-full object-cover"
        />
      </div>
      <div className="text-center space-y-1">
        <h2 className="text-lg">How can I help?</h2>
        <p className="text-sm text-muted-foreground">Ask about your homelab, containers, or system health.</p>
      </div>
      <div className="flex flex-wrap justify-center gap-2 mt-2">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onSuggestion(s)}
            className="rounded-full border bg-card px-4 py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function ChatPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const resumeSessionId = searchParams.get("session");

  // Restore session from sessionStorage if no explicit session param
  const [sessionId, setSessionId] = useState<string | null>(() => {
    if (resumeSessionId) return resumeSessionId;
    if (typeof window !== "undefined") {
      return sessionStorage.getItem(SESSION_KEY);
    }
    return null;
  });
  const [creating, setCreating] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [approvalRequest, setApprovalRequest] =
    useState<WsApprovalRequest | null>(null);
  const [agentState, setAgentState] = useState<AgentState>(null);
  const [activeToolName, setActiveToolName] = useState<string | undefined>();

  // Track streaming state with a ref to avoid closure staleness
  const chatInputRef = useRef<ChatInputHandle>(null);
  const streamingRef = useRef({ text: "", id: "", finalized: false });
  const msgIdCounter = useRef(0);
  const nextId = () => `msg-${++msgIdCounter.current}`;

  // Persist session ID
  useEffect(() => {
    if (sessionId) {
      sessionStorage.setItem(SESSION_KEY, sessionId);
    }
  }, [sessionId]);

  // Load prior messages when reconnecting to an existing session
  const [historyLoaded, setHistoryLoaded] = useState(false);

  useEffect(() => {
    if (!sessionId || historyLoaded) return;
    setHistoryLoaded(true);

    apiGet<MessageInfo[]>(`/api/sessions/${sessionId}/messages`)
      .then((msgs) => {
        if (!msgs || msgs.length === 0) return;
        const prior: ChatMessage[] = msgs
          .filter((m) => m.content)
          .map((m) => ({
            id: nextId(),
            role: m.role as "user" | "assistant",
            content: m.content!,
          }));
        setMessages(prior);
      })
      .catch(() => {
        // No history — new session or session not yet persisted
      });
  }, [sessionId, historyLoaded]);

  const { status, send, setOnMessage } = useWebSocket(sessionId);

  // Handle incoming WS messages
  useEffect(() => {
    setOnMessage((wsMsg) => {
      const sr = streamingRef.current;

      switch (wsMsg.type) {
        case "token":
          setAgentState("streaming");
          setActiveToolName(undefined);
          sr.finalized = false;
          if (!sr.id) {
            sr.id = nextId();
            sr.text = wsMsg.content;
            setMessages((prev) => [
              ...prev,
              { id: sr.id, role: "assistant", content: sr.text, isStreaming: true },
            ]);
          } else {
            sr.text += wsMsg.content;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === sr.id
                  ? { ...m, content: sr.text }
                  : m
              )
            );
          }
          break;

        case "message_complete":
          setAgentState(null);
          setActiveToolName(undefined);
          if (sr.id) {
            const finalId = sr.id;
            const finalText = sr.text;
            sr.id = "";
            sr.text = "";
            sr.finalized = true;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === finalId
                  ? { ...m, content: finalText, isStreaming: false }
                  : m
              )
            );
          } else if (wsMsg.content && !sr.finalized) {
            sr.finalized = true;
            setMessages((prev) => [
              ...prev,
              { id: nextId(), role: "assistant", content: wsMsg.content },
            ]);
          }
          break;

        case "tool_call":
          setAgentState("tool");
          setActiveToolName(wsMsg.name);
          if (sr.id && sr.text) {
            const finalId = sr.id;
            const finalText = sr.text;
            sr.id = "";
            sr.text = "";
            setMessages((prev) =>
              prev.map((m) =>
                m.id === finalId
                  ? { ...m, content: finalText, isStreaming: false }
                  : m
              )
            );
          }
          setMessages((prev) => [
            ...prev,
            {
              id: nextId(),
              role: "tool",
              content: `Calling ${wsMsg.name}(${JSON.stringify(wsMsg.args)})`,
              toolName: wsMsg.name,
            },
          ]);
          break;

        case "tool_result":
          setAgentState("thinking");
          setActiveToolName(undefined);
          setMessages((prev) => [
            ...prev,
            {
              id: nextId(),
              role: "tool",
              content: wsMsg.output.substring(0, 200),
              toolName: wsMsg.name,
            },
          ]);
          break;

        case "approval_request":
          setApprovalRequest(wsMsg);
          break;

        case "error":
          setAgentState(null);
          setActiveToolName(undefined);
          setMessages((prev) => [
            ...prev,
            { id: nextId(), role: "system", content: wsMsg.message },
          ]);
          break;
      }
    });
  }, [setOnMessage]);

  // Create a new session if needed
  useEffect(() => {
    if (sessionId || creating) return;
    setCreating(true);
    apiPost<{ session_id: string }>("/api/chat/sessions")
      .then((res) => {
        setSessionId(res.session_id);
      })
      .catch((err) => console.error("Failed to create session:", err))
      .finally(() => setCreating(false));
  }, [sessionId, creating]);

  const handleSend = useCallback(
    (text: string) => {
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "user", content: text },
      ]);
      setAgentState("thinking");
      send({ type: "message", content: text });
    },
    [send]
  );

  const handleApproval = useCallback(
    (requestId: string, approved: boolean) => {
      send({ type: "approval_response", request_id: requestId, approved });
      setApprovalRequest(null);
    },
    [send]
  );

  const handleStop = useCallback(() => {
    send({ type: "stop_generation" });
    setApprovalRequest(null);
    setAgentState(null);
    setActiveToolName(undefined);
    // Finalize any in-progress streaming bubble
    const sr = streamingRef.current;
    if (sr.id && sr.text) {
      const finalId = sr.id;
      const finalText = sr.text;
      sr.id = "";
      sr.text = "";
      sr.finalized = true;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === finalId
            ? { ...m, content: finalText, isStreaming: false }
            : m
        )
      );
    }
  }, [send]);

  const handleNewChat = useCallback(() => {
    sessionStorage.removeItem(SESSION_KEY);
    setSessionId(null);
    setMessages([]);
    setHistoryLoaded(false);
    streamingRef.current = { text: "", id: "", finalized: false };
    router.replace("/chat");
    requestAnimationFrame(() => chatInputRef.current?.focus());
  }, [router]);

  if (!sessionId) {
    return (
      <div className="flex items-center justify-center h-full">
        <Skeleton className="h-8 w-48" />
      </div>
    );
  }

  const hasMessages = messages.length > 0;

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ maxHeight: "calc(100vh - 5rem)" }}>
      <div className="flex items-center gap-2 px-4 py-2 border-b shrink-0 bg-card">
        <h1 className="text-lg">Chat</h1>
        <ConnectionDot status={status} />
        <Button variant="ghost" size="icon" onClick={handleNewChat} className="ml-auto">
          <SquarePen className="h-4 w-4" />
        </Button>
      </div>

      {hasMessages ? (
        <MessageList messages={messages} agentState={agentState} activeToolName={activeToolName} onStop={handleStop} />
      ) : (
        <WelcomeState onSuggestion={handleSend} />
      )}
      <ChatInput
        ref={chatInputRef}
        onSend={handleSend}
        disabled={status !== "connected"}
        isGenerating={agentState !== null}
      />
      <ApprovalDialog request={approvalRequest} onRespond={handleApproval} />
    </div>
  );
}
