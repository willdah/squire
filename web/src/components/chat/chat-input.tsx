"use client";

import { useState, useCallback, useRef, useEffect, useImperativeHandle, forwardRef } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send } from "lucide-react";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  isGenerating?: boolean;
}

export interface ChatInputHandle {
  focus: () => void;
}

export const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(
  function ChatInput({ onSend, disabled, isGenerating }, ref) {
    const [value, setValue] = useState("");
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useImperativeHandle(ref, () => ({
      focus: () => textareaRef.current?.focus(),
    }));

    // Focus whenever the textarea becomes enabled (covers initial mount,
    // new-chat reconnection, and any other disabled→enabled transition).
    useEffect(() => {
      if (!disabled) {
        textareaRef.current?.focus();
      }
    }, [disabled]);

    const canSend = !disabled && !isGenerating;

    const handleSubmit = useCallback(() => {
      const trimmed = value.trim();
      if (!trimmed || !canSend) return;
      onSend(trimmed);
      setValue("");
    }, [value, canSend, onSend]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    };

    return (
      <div className="flex items-end gap-2 border-t p-4">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask Squire something..."
          className="min-h-[44px] max-h-[200px] resize-none"
          disabled={disabled}
          rows={1}
        />
        <Button
          size="icon"
          onClick={handleSubmit}
          disabled={!canSend || !value.trim()}
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    );
  }
);
