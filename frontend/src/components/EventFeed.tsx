import { useEffect, useRef, useState } from "react";

interface Ev {
  topic: string;
  source: string;
  ts: number;
  payload: Record<string, unknown>;
}

const MAX_BACKOFF_MS = 4000;

export function EventFeed() {
  const [events, setEvents] = useState<Ev[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let stopped = false;
    let reconnectTimer: number | null = null;
    let attempt = 0;

    function connect() {
      if (stopped) return;
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${window.location.host}/ws/events`);
      wsRef.current = ws;

      ws.onopen = () => {
        attempt = 0;
      };

      ws.onclose = () => {
        if (stopped) return;
        const delay = Math.min(400 * 2 ** attempt, MAX_BACKOFF_MS);
        attempt += 1;
        reconnectTimer = window.setTimeout(connect, delay);
      };

      ws.onerror = () => {
        try { ws.close(); } catch { /* ignore */ }
      };

      ws.onmessage = (msg) => {
        try {
          const env = JSON.parse(msg.data);
          if (env.type === "event") {
            setEvents((es) => [env.data as Ev, ...es].slice(0, 200));
          }
        } catch {
          /* ignore */
        }
      };
    }

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      try { wsRef.current?.close(); } catch { /* ignore */ }
    };
  }, []);

  return (
    <div className="events">
      {events.length === 0 && <div className="ev">no events yet…</div>}
      {events.map((e, i) => (
        <div key={i} className="ev">
          <span className="topic">{e.topic}</span>
          <span className="src">{e.source}</span>
        </div>
      ))}
    </div>
  );
}
