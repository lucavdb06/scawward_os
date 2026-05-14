import { useEffect, useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { EventFeed } from "./components/EventFeed";
import { useHealth } from "./hooks/useHealth";

export default function App() {
  const { health, refresh } = useHealth();
  const [now, setNow] = useState(new Date());
  const [ollamaPick, setOllamaPick] = useState("");
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (health?.llm_provider === "ollama" && health.llm_model) {
      setOllamaPick(health.llm_model);
    }
  }, [health?.llm_provider, health?.llm_model]);

  async function applyLlm(provider: "anthropic" | "ollama") {
    if (!health) return;
    setSwitching(true);
    try {
      const body =
        provider === "ollama"
          ? {
              provider,
              ollama_model:
                ollamaPick ||
                health.ollama_models[0] ||
                health.llm_model ||
                "llama3.1:latest",
            }
          : { provider };
      const r = await fetch("/api/llm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const t = await r.text();
        alert(`LLM switch failed: ${t}`);
      } else {
        refresh();
      }
    } finally {
      setSwitching(false);
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">S C A W W A R D</div>
        <div className="status">
          v{health?.version ?? "…"}{" "}
          <span className="dim">·</span> tools:{health?.tools.length ?? "?"}
        </div>
        <div className="status llm-row">
          {health?.llm_ready ? (
            <span className="ok-dot">
              ● {health.llm_provider} · {health.llm_model}
            </span>
          ) : (
            <span className="warn-dot">
              ○ {health?.llm_provider ?? "…"} — add API key or start Ollama
            </span>
          )}
          {health && (
            <>
              <select
                className="llm-select"
                disabled={switching}
                value={health.llm_provider}
                onChange={(e) => {
                  const v = e.target.value as "anthropic" | "ollama";
                  void applyLlm(v);
                }}
                title="Switch LLM backend"
              >
                <option value="anthropic">Claude (API)</option>
                <option value="ollama">
                  Ollama {!health.ollama_reachable ? "(offline)" : ""}
                </option>
              </select>
              {health.llm_provider === "ollama" && health.ollama_models.length > 0 && (
                <select
                  className="llm-select narrow"
                  disabled={switching}
                  value={ollamaPick || health.llm_model}
                  onChange={(e) => {
                    setOllamaPick(e.target.value);
                    setSwitching(true);
                    fetch("/api/llm", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        provider: "ollama",
                        ollama_model: e.target.value,
                      }),
                    })
                      .then((r) => {
                        if (!r.ok) return r.text().then((t) => Promise.reject(new Error(t)));
                      })
                      .then(() => refresh())
                      .catch((err) => alert(String(err)))
                      .finally(() => setSwitching(false));
                  }}
                  title="Local model"
                >
                  {health.ollama_models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              )}
            </>
          )}
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
