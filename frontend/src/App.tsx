import { useEffect, useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { EventFeed } from "./components/EventFeed";
import { useHealth } from "./hooks/useHealth";

export default function App() {
  const health = useHealth();
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const apiOK = health?.has_api_key ?? null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">S C A W W A R D</div>
        <div className="status">
          v{health?.version ?? "…"}{" "}
          <span className="dim">·</span> tools:{health?.tools.length ?? "?"}
        </div>
        <div className="status">
          {apiOK === null && <span className="dim">api:…</span>}
          {apiOK === true && <span className="ok-dot">● claude online</span>}
          {apiOK === false && <span className="bad-dot">● no api key</span>}
        </div>
        <div className="status" style={{ marginLeft: "auto" }}>
          {now.toLocaleTimeString()}
        </div>
      </header>

      <ChatPanel />
      <aside className="sidebar">
        <h3>EVENT FEED</h3>
        <EventFeed />
      </aside>
    </div>
  );
}
