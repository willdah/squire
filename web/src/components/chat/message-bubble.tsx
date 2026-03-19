"use client";

/* eslint-disable @next/next/no-img-element */
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "./message-list";
import { User, Wrench } from "lucide-react";

const SKILL_MARKER_RE = /^\[SKILL\s+COMPLETE\]\s*$/gim;

function stripSkillMarkers(text: string): string {
  return text.replace(SKILL_MARKER_RE, "").replace(/\n{3,}/g, "\n\n").trim();
}

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const { role, content, toolName, isStreaming } = message;

  if (role === "tool") {
    return (
      <div className="flex items-start gap-2 text-xs text-muted-foreground px-2 py-1 ml-10 animate-fade-in">
        <Wrench className="h-3 w-3 mt-0.5 shrink-0" />
        <span>
          <span className="font-medium">{toolName}</span>: {content}
        </span>
      </div>
    );
  }

  if (role === "system") {
    return (
      <div className="text-muted-foreground text-xs italic px-2 py-1 ml-10 animate-fade-in">
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
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
            <User className="h-4 w-4 text-muted-foreground" />
          </div>
        ) : (
          <div className="h-8 w-8 rounded-full overflow-hidden bg-muted shrink-0">
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
          "max-w-[80%] rounded-lg px-4 py-3 text-sm",
          isUser
            ? "bg-gradient-to-br from-primary to-primary/90 text-primary-foreground"
            : "bg-card border",
          isStreaming && "border-primary/30 shadow-[0_0_12px_-3px] shadow-primary/20"
        )}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{content}</span>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ className, children, ...props }) {
                  const isBlock = className?.includes("language-");
                  if (isBlock) {
                    return (
                      <pre className="bg-muted rounded-md p-3 font-mono text-xs overflow-x-auto">
                        <code className={className} {...props}>{children}</code>
                      </pre>
                    );
                  }
                  return (
                    <code className="bg-muted rounded px-1.5 py-0.5 font-mono text-xs" {...props}>
                      {children}
                    </code>
                  );
                },
                pre({ children }) {
                  return <>{children}</>;
                },
              }}
            >
              {stripSkillMarkers(content)}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
