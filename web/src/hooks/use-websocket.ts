"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { wsUrl } from "@/lib/api";
import type { WsServerMessage } from "@/lib/types";

export type WsStatus = "connecting" | "connected" | "disconnected";

const MAX_RETRIES = 5;
const BASE_DELAY_MS = 1000;

export function useWebSocket(sessionId: string | null, queryParams?: Record<string, string>) {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<WsStatus>("disconnected");
  const onMessageRef = useRef<((msg: WsServerMessage) => void) | null>(null);
  const retriesRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Track intentional close to avoid reconnecting on unmount
  const intentionalCloseRef = useRef(false);

  // Serialize queryParams to a stable string for the dependency array
  const queryString = queryParams
    ? Object.entries(queryParams)
        .filter(([, v]) => v)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
        .join("&")
    : "";

  useEffect(() => {
    if (!sessionId) return;

    intentionalCloseRef.current = false;

    function connect() {
      const qs = queryString ? `?${queryString}` : "";
      const ws = new WebSocket(wsUrl(`/api/chat/ws/${sessionId}${qs}`));
      wsRef.current = ws;
      setStatus("connecting");

      ws.onopen = () => {
        setStatus("connected");
        retriesRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const msg: WsServerMessage = JSON.parse(event.data);
          onMessageRef.current?.(msg);
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        if (intentionalCloseRef.current) {
          setStatus("disconnected");
          return;
        }
        // Reconnect with exponential backoff
        if (retriesRef.current < MAX_RETRIES) {
          const delay = BASE_DELAY_MS * Math.pow(2, retriesRef.current);
          retriesRef.current++;
          setStatus("connecting");
          retryTimerRef.current = setTimeout(connect, delay);
        } else {
          setStatus("disconnected");
        }
      };

      ws.onerror = () => {
        // onclose will fire after onerror — reconnect logic lives there
      };
    }

    connect();

    return () => {
      intentionalCloseRef.current = true;
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [sessionId, queryString]);

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
