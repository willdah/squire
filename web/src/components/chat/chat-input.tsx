"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { ArrowUp, Box, Layers, Server, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useChatAutocompleteData } from "@/hooks/use-chat-autocomplete-data";
import type { MentionCandidate } from "@/lib/chat/mention-candidates";
import { filterMentionCandidates } from "@/lib/chat/mention-candidates";
import {
  filterSlashCommands,
  getActiveAutocompleteMode,
  type SlashCommandDef,
} from "@/lib/chat/slash-commands";
import { transformOutgoingMessage } from "@/lib/chat/transform-outgoing";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  isGenerating?: boolean;
}

export interface ChatInputHandle {
  focus: () => void;
}

type MenuRow = { type: "slash"; def: SlashCommandDef } | { type: "mention"; cand: MentionCandidate };

const MENTION_MENU_MAX = 50;

function KindIcon({ kind }: { kind: MentionCandidate["kind"] }) {
  const cls = "h-3.5 w-3.5 shrink-0 text-muted-foreground";
  switch (kind) {
    case "host":
      return <Server className={cls} aria-hidden />;
    case "container":
      return <Box className={cls} aria-hidden />;
    case "tool":
      return <Wrench className={cls} aria-hidden />;
    case "service":
      return <Layers className={cls} aria-hidden />;
    default:
      return null;
  }
}

export const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(
  function ChatInput({ onSend, disabled, isGenerating }, ref) {
    const [value, setValue] = useState("");
    const [cursor, setCursor] = useState(0);
    const [menuOpen, setMenuOpen] = useState(false);
    const [menuRows, setMenuRows] = useState<MenuRow[]>([]);
    const [selectedIndex, setSelectedIndex] = useState(0);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const menuRef = useRef<HTMLDivElement>(null);
    const { candidates: mentionCandidates, expansionByToken } = useChatAutocompleteData();

    useImperativeHandle(ref, () => ({
      focus: () => textareaRef.current?.focus(),
    }));

    useEffect(() => {
      if (!disabled) {
        textareaRef.current?.focus();
      }
    }, [disabled]);

    useEffect(() => {
      const container = menuRef.current;
      if (!container || !menuOpen) return;
      const item = container.children[selectedIndex] as HTMLElement | undefined;
      item?.scrollIntoView({ block: "nearest" });
    }, [selectedIndex, menuOpen]);

    const canSend = !disabled && !isGenerating;

    const updateMenu = useCallback(
      (nextValue: string, nextCursor: number) => {
        const active = getActiveAutocompleteMode(nextValue, nextCursor);
        if (!active) {
          setMenuOpen(false);
          setMenuRows([]);
          return;
        }
        if (active.mode === "slash") {
          const q = active.segment.query;
          const defs = filterSlashCommands(q);
          const rows: MenuRow[] = defs.map((def) => ({ type: "slash", def }));
          setMenuRows(rows);
          setMenuOpen(rows.length > 0);
          setSelectedIndex(0);
          return;
        }
        const q = active.segment.query;
        const filtered = filterMentionCandidates(mentionCandidates, q).slice(0, MENTION_MENU_MAX);
        const rows: MenuRow[] = filtered.map((cand) => ({ type: "mention", cand }));
        setMenuRows(rows);
        setMenuOpen(rows.length > 0);
        setSelectedIndex(0);
      },
      [mentionCandidates]
    );

    const syncCursorAndMenu = useCallback(
      (el: HTMLTextAreaElement) => {
        const pos = el.selectionStart ?? 0;
        setCursor(pos);
        updateMenu(el.value, pos);
      },
      [updateMenu]
    );

    const applyMenuSelection = useCallback(
      (row: MenuRow) => {
        const ta = textareaRef.current;
        if (!ta) return;
        const pos = ta.selectionStart ?? cursor;
        const active = getActiveAutocompleteMode(value, pos);
        if (!active) {
          setMenuOpen(false);
          return;
        }
        const { start, end } = active.segment;
        let insert: string;
        if (row.type === "slash") {
          insert = row.def.insert;
        } else {
          insert = row.cand.insertText;
          if (!/\s$/.test(insert)) {
            insert += " ";
          }
        }
        const newValue = value.slice(0, start) + insert + value.slice(end);
        setValue(newValue);
        const newPos = start + insert.length;
        setMenuOpen(false);
        setMenuRows([]);
        requestAnimationFrame(() => {
          ta.focus();
          ta.setSelectionRange(newPos, newPos);
          setCursor(newPos);
        });
      },
      [value, cursor]
    );

    const handleSubmit = useCallback(() => {
      const trimmed = value.trim();
      if (!trimmed || !canSend) return;
      const out = transformOutgoingMessage(trimmed, expansionByToken);
      onSend(out);
      setValue("");
      setMenuOpen(false);
      setMenuRows([]);
    }, [value, canSend, expansionByToken, onSend]);

    const handleKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (menuOpen && menuRows.length > 0) {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setSelectedIndex((i) => Math.min(i + 1, menuRows.length - 1));
            return;
          }
          if (e.key === "ArrowUp") {
            e.preventDefault();
            setSelectedIndex((i) => Math.max(i - 1, 0));
            return;
          }
          if (e.key === "Escape") {
            e.preventDefault();
            setMenuOpen(false);
            setMenuRows([]);
            return;
          }
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            const row = menuRows[selectedIndex];
            if (row) applyMenuSelection(row);
            return;
          }
        }
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          handleSubmit();
        }
      },
      [menuOpen, menuRows, selectedIndex, applyMenuSelection, handleSubmit]
    );

    const listId = useMemo(() => "chat-input-autocomplete", []);

    return (
      <div className="relative flex items-end gap-2 border-t border-border/60 bg-card/50 p-4">
        {menuOpen && menuRows.length > 0 ? (
          <div
            ref={menuRef}
            id={listId}
            role="listbox"
            className="absolute bottom-full left-4 right-16 z-50 mb-1 max-h-52 overflow-y-auto rounded-lg border border-border/80 bg-popover text-popover-foreground shadow-md"
            onMouseDown={(e) => e.preventDefault()}
          >
            {menuRows.map((row, idx) => (
              <button
                key={
                  row.type === "slash"
                    ? `slash-${row.def.id}`
                    : `mention-${row.cand.kind}-${row.cand.token}`
                }
                type="button"
                role="option"
                aria-selected={idx === selectedIndex}
                className={`flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-accent/80 ${
                  idx === selectedIndex ? "bg-accent/60" : ""
                }`}
                onMouseEnter={() => setSelectedIndex(idx)}
                onClick={() => applyMenuSelection(row)}
              >
                {row.type === "slash" ? (
                  <span className="mt-0.5 font-mono text-xs text-primary shrink-0">{row.def.insert.trim()}</span>
                ) : (
                  <KindIcon kind={row.cand.kind} />
                )}
                <span className="min-w-0 flex-1">
                  <span className="block font-medium leading-tight">
                    {row.type === "slash" ? row.def.description : row.cand.label}
                  </span>
                  {row.type === "mention" && row.cand.subtitle ? (
                    <span className="block text-xs text-muted-foreground truncate">{row.cand.subtitle}</span>
                  ) : null}
                </span>
              </button>
            ))}
          </div>
        ) : null}

        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            const pos = e.target.selectionStart ?? e.target.value.length;
            setCursor(pos);
            updateMenu(e.target.value, pos);
          }}
          onClick={(e) => syncCursorAndMenu(e.currentTarget)}
          onSelect={(e) => syncCursorAndMenu(e.currentTarget)}
          onKeyUp={(e) => {
            const k = e.key;
            if (k === "ArrowDown" || k === "ArrowUp" || k === "Enter" || k === "Escape") return;
            syncCursorAndMenu(e.currentTarget);
          }}
          onKeyDown={handleKeyDown}
          placeholder="Ask Squire something… Type / for commands or @ for hosts, containers, tools…"
          className="min-h-[44px] max-h-[200px] min-w-0 flex-1 resize-none bg-background"
          disabled={disabled}
          rows={1}
          aria-expanded={menuOpen}
          aria-controls={menuOpen ? listId : undefined}
          aria-autocomplete="list"
        />
        <Button
          size="icon"
          onClick={handleSubmit}
          disabled={!canSend || !value.trim()}
          className="rounded-lg shrink-0"
        >
          <ArrowUp className="h-4 w-4" />
        </Button>
      </div>
    );
  }
);
