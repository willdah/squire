"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { wsUrl } from "@/lib/api";
import type { WatchEvent } from "@/lib/types";

export type WatchWsStatus = "connecting" | "connected" | "disconnected";

const MAX_RETRIES = 5;
const BASE_DELAY_MS = 1000;

export function useWatchWebSocket(enabled: boolean = true) {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<WatchWsStatus>("disconnected");
  const [events, setEvents] = useState<WatchEvent[]>([]);
  const intentionalCloseRef = useRef(false);
  const retriesRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled) {
      setStatus("disconnected");
      return;
    }

    intentionalCloseRef.current = false;

    function connect() {
      const ws = new WebSocket(wsUrl("/api/watch/ws"));
      wsRef.current = ws;
      setStatus("connecting");

      ws.onopen = () => {
        setStatus("connected");
        retriesRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const watchEvent: WatchEvent = JSON.parse(event.data);
          setEvents((prev) => [...prev, watchEvent]);
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
        if (retriesRef.current < MAX_RETRIES) {
          const delay = BASE_DELAY_MS * Math.pow(2, retriesRef.current);
          retriesRef.current++;
          setStatus("connecting");
          retryTimerRef.current = setTimeout(connect, delay);
        } else {
          setStatus("disconnected");
        }
      };

      ws.onerror = () => {};
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
  }, [enabled]);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { status, events, clearEvents };
}
