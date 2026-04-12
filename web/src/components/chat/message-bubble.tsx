"use client";

/* eslint-disable @next/next/no-img-element */
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "./message-list";
import { User, Wrench, Copy, Check } from "lucide-react";
import { useState, useCallback } from "react";

const SKILL_MARKER_RE = /^\[SKILL\s+COMPLETE\]\s*$/gim;

const RAW_TOOL_CALL_RE =
  /\{\s*"name"\s*:\s*"[^"]+"\s*,\s*"parameters"\s*:\s*\{[^}]*\}\s*\}/g;

function stripSkillMarkers(text: string): string {
  return text.replace(SKILL_MARKER_RE, "").replace(/\n{3,}/g, "\n\n").trim();
}

function stripRawToolCalls(text: string): string {
  return text.replace(RAW_TOOL_CALL_RE, "").replace(/\n{3,}/g, "\n\n").trim();
}

function CodeBlock({ className, children }: { className?: string; children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const text = String(children).replace(/\n$/, "");
  const lang = className?.replace("language-", "") || "";

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [text]);

  return (
    <div className="group/code relative">
      {lang && (
        <div className="flex items-center justify-between px-3 pt-2 pb-0">
          <span className="text-[10px] font-mono font-medium uppercase tracking-wider text-muted-foreground/50">{lang}</span>
        </div>
      )}
      <pre className="bg-muted/60 rounded-lg p-3 font-mono text-xs leading-relaxed overflow-x-auto ring-1 ring-border/20">
        <code className={className}>{children}</code>
      </pre>
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1 rounded-md bg-muted/80 opacity-0 group-hover/code:opacity-100 transition-opacity text-muted-foreground hover:text-foreground"
        title="Copy"
      >
        {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
      </button>
    </div>
  );
}

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const { role, content, toolName, isStreaming, inputTokens, outputTokens, totalTokens } = message;

  const cleanContent =
    role === "assistant" ? stripRawToolCalls(stripSkillMarkers(content)) : content;

  if (role === "assistant" && !cleanContent.trim() && !isStreaming) {
    return null;
  }

  if (role === "tool") {
    return (
      <div className="flex items-start gap-2 text-xs text-muted-foreground px-2 py-1 ml-11 animate-fade-in">
        <Wrench className="h-3 w-3 mt-0.5 shrink-0 text-primary/50" />
        <span>
          <span className="font-medium text-foreground/70">{toolName}</span>{" "}
          <span className="opacity-75">{content}</span>
        </span>
      </div>
    );
  }

  if (role === "system") {
    return (
      <div className="text-muted-foreground text-xs italic px-2 py-1 ml-11 animate-fade-in">
        {content}
      </div>
    );
  }

  const isUser = role === "user";

  return (
    <div
      className={cn(
        "flex items-start gap-3 animate-fade-in",
        isUser && "flex-row-reverse"
      )}
    >
      {/* Avatar */}
      <div className="shrink-0 mt-0.5">
        {isUser ? (
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10">
            <User className="h-4 w-4 text-primary/70" />
          </div>
        ) : (
          <div className="h-8 w-8 rounded-full overflow-hidden bg-muted shrink-0 ring-1 ring-border/50">
            <img
              src="/squire-avatar.png"
              alt="Squire"
              className="h-full w-full object-cover"
            />
          </div>
        )}
      </div>

      {/* Bubble */}
      <div
        className={cn(
          "max-w-[80%] rounded-xl px-4 py-3 text-sm",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-card ring-1 ring-border/50",
          isStreaming && "ring-1 ring-primary/30 shadow-[0_0_16px_-4px] shadow-primary/15"
        )}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{content}</span>
        ) : (
          <div className="space-y-2">
            <div className="chat-prose">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ className, children, ...props }) {
                    const isBlock = className?.includes("language-");
                    if (isBlock) {
                      return <CodeBlock className={className}>{children}</CodeBlock>;
                    }
                    return (
                      <code {...props}>
                        {children}
                      </code>
                    );
                  },
                  pre({ children }) {
                    return <>{children}</>;
                  },
                }}
              >
                {cleanContent}
              </ReactMarkdown>
            </div>
            {(inputTokens !== undefined || outputTokens !== undefined || totalTokens !== undefined) && (
              <div className="text-[11px] text-muted-foreground">
                tokens in/out/total: {inputTokens ?? "—"} / {outputTokens ?? "—"} / {totalTokens ?? "—"}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
