"use client";

/* eslint-disable @next/next/no-img-element */
import { Suspense, startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { apiGet, apiPatch, apiPost } from "@/lib/api";
import { useWebSocket } from "@/hooks/use-websocket";
import { MessageList, type ChatMessage, type AgentState } from "@/components/chat/message-list";
import { ChatInput, type ChatInputHandle } from "@/components/chat/chat-input";
import { ApprovalDialog } from "@/components/chat/approval-dialog";
import type { ConfigDetailResponse, LLMModelsResponse, MessageInfo, WsApprovalRequest } from "@/lib/types";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Check, Loader2, SquarePen } from "lucide-react";

const SESSION_KEY = "squire_chat_session";

const suggestions = [
  "Show system status",
  "Check containers",
  "List alerts",
];

function configErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) return "Failed to update model.";
  const body = error.message.match(/^API error \d+: (.*)$/)?.[1];
  if (!body) return error.message;
  try {
    const parsed = JSON.parse(body) as { detail?: string };
    return parsed.detail ?? error.message;
  } catch {
    return error.message;
  }
}

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
    <div className="flex-1 flex flex-col items-center justify-center gap-5 px-4">
      <div className="animate-fade-in-up h-14 w-14 rounded-2xl overflow-hidden bg-primary/10 ring-1 ring-primary/20 flex items-center justify-center">
        <img
          src="/squire-avatar.png"
          alt="Squire"
          className="h-full w-full object-cover"
        />
      </div>
      <div className="text-center space-y-1.5 animate-stagger-1">
        <h2 className="font-display text-xl font-semibold">How can I help?</h2>
        <p className="text-sm text-muted-foreground">Ask about your homelab, containers, or system health.</p>
      </div>
      <div className="flex flex-wrap justify-center gap-2 mt-1 animate-stagger-2">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onSuggestion(s)}
            className="rounded-full ring-1 ring-border/60 bg-card px-4 py-2 text-sm text-muted-foreground hover:bg-primary/8 hover:text-foreground hover:ring-primary/30 transition-all duration-200"
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
  const skillName = searchParams.get("skill");

  // Restore session from sessionStorage if no explicit session param.
  // When executing a skill, always start fresh (don't reuse old session).
  const [sessionId, setSessionId] = useState<string | null>(() => {
    if (skillName) return null;
    if (resumeSessionId) return resumeSessionId;
    if (typeof window !== "undefined") {
      return sessionStorage.getItem(SESSION_KEY);
    }
    return null;
  });
  const creatingRef = useRef(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [approvalRequest, setApprovalRequest] =
    useState<WsApprovalRequest | null>(null);
  const [agentState, setAgentState] = useState<AgentState>(null);
  const [activeToolName, setActiveToolName] = useState<string | undefined>();
  const [activeModel, setActiveModel] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [modelProvider, setModelProvider] = useState<string>("");
  const [modelLoading, setModelLoading] = useState(true);
  const [modelSaving, setModelSaving] = useState(false);
  const [modelError, setModelError] = useState<string | null>(null);

  // Size the model dropdown trigger to fit the longest option so the layout
  // stays stable regardless of which model is selected. Uses `ch` units
  // because the trigger is rendered in a monospace font.
  const longestModelLen = useMemo(
    () => modelOptions.reduce((max, opt) => Math.max(max, opt.length), 0),
    [modelOptions],
  );

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
  const historyLoadedRef = useRef(false);

  useEffect(() => {
    if (!sessionId || historyLoadedRef.current) return;
    historyLoadedRef.current = true;

    apiGet<MessageInfo[]>(`/api/sessions/${sessionId}/messages`)
      .then((msgs) => {
        if (!msgs || msgs.length === 0) return;
        const prior: ChatMessage[] = msgs
          .filter((m) => m.content)
          .map((m) => ({
            id: nextId(),
            role: m.role as "user" | "assistant",
            content: m.content!,
            inputTokens: m.input_tokens,
            outputTokens: m.output_tokens,
            totalTokens: m.total_tokens,
          }));
        setMessages(prior);
      })
      .catch(() => {
        // No history — new session or session not yet persisted
      });
  }, [sessionId]);

  const wsQueryParams = skillName ? { skill: skillName } : undefined;
  const { status, send, setOnMessage, reconnect } = useWebSocket(sessionId, wsQueryParams);

  useEffect(() => {
    let cancelled = false;
    setModelLoading(true);
    Promise.all([
      apiGet<ConfigDetailResponse>("/api/config"),
      apiGet<LLMModelsResponse>("/api/config/llm/models"),
    ])
      .then(([config, modelsResponse]) => {
        if (cancelled) return;
        const model = String(config.llm?.values?.model ?? modelsResponse.current_model ?? "");
        setActiveModel(model);
        setSelectedModel(model);
        setModelProvider(modelsResponse.provider);
        setModelOptions(Array.from(new Set([...(modelsResponse.models ?? []), model])).sort());
        if (modelsResponse.error) {
          setModelError(`Model provider lookup failed: ${modelsResponse.error}`);
        }
      })
      .catch((error) => {
        if (cancelled) return;
        setModelError(configErrorMessage(error));
      })
      .finally(() => {
        if (!cancelled) setModelLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
          if (wsMsg.stopped) {
            sr.id = "";
            sr.text = "";
            sr.finalized = true;
            break;
          }
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

  // Auto-send initial message for skill execution once WebSocket connects.
  const skillSentRef = useRef(false);
  useEffect(() => {
    if (!skillName || skillSentRef.current || status !== "connected") return;
    skillSentRef.current = true;
    const text = `Execute your active skill "${skillName}" now. Use your tools.`;
    const displayText = `Execute skill "${skillName}"`;
    startTransition(() => {
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "user", content: displayText },
      ]);
      setAgentState("thinking");
    });
    send({ type: "message", content: text });
  }, [skillName, status, send]);

  // Create a new session if needed
  useEffect(() => {
    if (sessionId || creatingRef.current) return;
    creatingRef.current = true;
    apiPost<{ session_id: string }>("/api/chat/sessions")
      .then((res) => {
        setSessionId(res.session_id);
      })
      .catch((err) => console.error("Failed to create session:", err))
      .finally(() => { creatingRef.current = false; });
  }, [sessionId]);

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
    historyLoadedRef.current = false;
    streamingRef.current = { text: "", id: "", finalized: false };
    router.replace("/chat");
    requestAnimationFrame(() => chatInputRef.current?.focus());
  }, [router]);

  const handleSaveModel = useCallback(async () => {
    const candidate = selectedModel.trim();
    if (!candidate) {
      setModelError("Model cannot be empty.");
      return;
    }
    if (candidate === activeModel) {
      setModelError(null);
      return;
    }

    setModelSaving(true);
    setModelError(null);
    try {
      await apiPatch("/api/config/llm?persist=true", { model: candidate });
      setActiveModel(candidate);
      setSelectedModel(candidate);
      reconnect();
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "system",
          content: `Model switched to ${candidate}. Reconnected this chat to use the new model.`,
        },
      ]);
    } catch (error) {
      const message = configErrorMessage(error);
      if (message.includes("Cannot update env-var-overridden fields")) {
        setModelError("Model is locked by SQUIRE_LLM_MODEL. Update the environment variable to change it.");
      } else {
        setModelError(message);
      }
    } finally {
      setModelSaving(false);
    }
  }, [activeModel, reconnect, selectedModel]);

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
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border/60 shrink-0 bg-card/80">
        <h1 className="text-base font-display font-semibold">Chat</h1>
        <ConnectionDot status={status} />
        <div className="ml-3 flex items-center gap-2 min-w-0">
          <span className="text-xs text-muted-foreground">
            Model{modelProvider ? ` (${modelProvider})` : ""}
          </span>
          {modelLoading ? (
            <Skeleton className="h-6 w-40" />
          ) : (
            <>
              <Select value={selectedModel} onValueChange={(value) => setSelectedModel(value ?? "")}>
                <SelectTrigger
                  className="h-8 min-w-48 max-w-[32rem] text-xs font-mono"
                  style={
                    longestModelLen
                      ? { width: `calc(${longestModelLen}ch + 2.5rem)` }
                      : undefined
                  }
                  aria-label="Active model"
                  disabled={modelSaving || modelOptions.length === 0}
                >
                  <SelectValue placeholder="No models available" />
                </SelectTrigger>
                <SelectContent>
                  {modelOptions.map((model) => (
                    <SelectItem key={model} value={model} className="font-mono text-xs">
                      {model}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                size="icon"
                variant="ghost"
                onClick={handleSaveModel}
                disabled={modelSaving || !selectedModel || selectedModel === activeModel}
                aria-label="Save model"
              >
                {modelSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
              </Button>
            </>
          )}
        </div>
        <Button variant="ghost" size="icon" onClick={handleNewChat} className="ml-auto">
          <SquarePen className="h-4 w-4" />
        </Button>
      </div>
      {modelError && (
        <div className="px-4 py-1 border-b border-border/40 text-xs text-destructive bg-destructive/5">
          {modelError}
        </div>
      )}

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
