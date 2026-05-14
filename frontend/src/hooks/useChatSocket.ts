import { useCallback, useEffect, useRef, useState } from "react";

export type ChatEvent =
  | { type: "text"; data: { text: string } }
  | { type: "tool"; data: { name: string; input: unknown; result: { ok?: boolean; summary?: string; data?: Record<string, unknown> } | null } }
  | { type: "usage"; data: { input: number; output: number; iteration: number } }
  | { type: "done"; data: Record<string, never> }
  | { type: "error"; data: { message: string } };

const MAX_BACKOFF_MS = 4000;

export function useChatSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const attemptRef = useRef(0);
  const stoppedRef = useRef(false);

  const [events, setEvents] = useState<ChatEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("/api/chat/history");
        if (!r.ok || cancelled) return;
        const data = (await r.json()) as { events?: ChatEvent[] };
        if (!cancelled && data.events && data.events.length > 0) {
          setEvents(data.events);
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    stoppedRef.current = false;

    function connect() {
      if (stoppedRef.current) return;

      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${window.location.host}/ws/chat`);
      wsRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        setConnected(true);
      };

      ws.onclose = () => {
        setConnected(false);
        setBusy(false);
        if (stoppedRef.current) return;
        const delay = Math.min(
          400 * 2 ** attemptRef.current,
          MAX_BACKOFF_MS,
        );
        attemptRef.current += 1;
        reconnectTimerRef.current = window.setTimeout(connect, delay);
      };

      ws.onerror = () => {
        try { ws.close(); } catch { /* ignore */ }
      };

      ws.onmessage = (msg) => {
        try {
          const ev = JSON.parse(msg.data) as ChatEvent;
          setEvents((es) => [...es, ev]);
          if (ev.type === "done" || ev.type === "error") setBusy(false);
        } catch {
          /* ignore */
        }
      };
    }

    connect();

    return () => {
      stoppedRef.current = true;
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
      }
      try { wsRef.current?.close(); } catch { /* ignore */ }
    };
  }, []);

  const send = useCallback((text: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    setBusy(true);
    setEvents((es) => [...es, { type: "text", data: { text: `\n> ${text}\n` } }]);
    ws.send(JSON.stringify({ text }));
  }, []);

  return { events, send, connected, busy };
}
