"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { wsUrl } from "@/lib/api";
import type { WsServerMessage } from "@/lib/types";

export type WsStatus = "connecting" | "connected" | "disconnected";

export function useWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<WsStatus>("disconnected");
  // Callback ref — consumers register a handler instead of reading a messages array
  const onMessageRef = useRef<((msg: WsServerMessage) => void) | null>(null);

  useEffect(() => {
    if (!sessionId) return;

    const ws = new WebSocket(wsUrl(`/api/chat/ws/${sessionId}`));
    wsRef.current = ws;
    setStatus("connecting");

    ws.onopen = () => setStatus("connected");

    ws.onmessage = (event) => {
      try {
        const msg: WsServerMessage = JSON.parse(event.data);
        onMessageRef.current?.(msg);
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setStatus("disconnected");
      wsRef.current = null;
    };

    ws.onerror = () => {
      setStatus("disconnected");
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [sessionId]);

  const send = useCallback(
    (data: Record<string, unknown>) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify(data));
      }
    },
    []
  );

  const setOnMessage = useCallback(
    (handler: (msg: WsServerMessage) => void) => {
      onMessageRef.current = handler;
    },
    []
  );

  return { status, send, setOnMessage };
}
