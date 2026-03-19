"use client";

import { useEffect, useRef } from "react";
import { MessageBubble } from "./message-bubble";
import { ThinkingIndicator } from "./thinking-indicator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Square } from "lucide-react";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  toolName?: string;
  isStreaming?: boolean;
}

export type AgentState = "thinking" | "tool" | "streaming" | null;

interface MessageListProps {
  messages: ChatMessage[];
  agentState?: AgentState;
  activeToolName?: string;
  onStop?: () => void;
}

export function MessageList({ messages, agentState, activeToolName, onStop }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, agentState]);

  return (
    <ScrollArea className="flex-1 min-h-0 px-4">
      <div className="space-y-3 py-4">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <ThinkingIndicator state={agentState ?? null} toolName={activeToolName} />
        {agentState && onStop && (
          <div className="flex justify-center py-1">
            <Button
              variant="outline"
              size="sm"
              onClick={onStop}
              className="h-7 gap-1.5 text-xs text-muted-foreground hover:text-destructive hover:border-destructive/50"
            >
              <Square className="h-3 w-3" />
              Stop
            </Button>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
