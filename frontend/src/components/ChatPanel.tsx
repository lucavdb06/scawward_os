import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChatSocket, ChatEvent } from "../hooks/useChatSocket";

type Turn =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string }
  | { role: "tool"; name: string; input: unknown; result: ToolResultLike | null }
  | { role: "error"; text: string };

interface ToolResultLike {
  ok?: boolean;
  summary?: string;
  data?: Record<string, unknown>;
}

function toolResultPreview(result: ToolResultLike | null): {
  ok: boolean;
  text: string;
} {
  if (!result) return { ok: false, text: "(no result)" };
  const ok = result.ok ?? false;
  const summary = result.summary ?? "(empty)";
  return { ok, text: summary };
}

function compactInput(input: unknown): string {
  if (input === null || input === undefined) return "";
  if (typeof input !== "object") return String(input);
  try {
    const j = JSON.stringify(input);
    return j.length > 90 ? j.slice(0, 87) + "…" : j;
  } catch {
    return "{...}";
  }
}

export function ChatPanel() {
  const { events, send, busy, connected } = useChatSocket();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const turns = useMemo<Turn[]>(() => {
    const out: Turn[] = [];
    let buffer = "";
    const flush = () => {
      if (buffer) {
        out.push({ role: "assistant", text: buffer });
        buffer = "";
      }
    };
    for (const ev of events as ChatEvent[]) {
      if (ev.type === "text") {
        const t = ev.data.text;
        if (t.startsWith("\n> ")) {
          flush();
          out.push({ role: "user", text: t.replace(/^\n> /, "").trim() });
        } else {
          buffer += t;
        }
      } else if (ev.type === "tool") {
        flush();
        out.push({
          role: "tool",
          name: ev.data.name,
          input: ev.data.input,
          result: (ev.data.result ?? null) as ToolResultLike | null,
        });
      } else if (ev.type === "done") {
        flush();
      } else if (ev.type === "error") {
        flush();
        out.push({ role: "error", text: ev.data.message });
      }
    }
    if (buffer) out.push({ role: "assistant", text: buffer });
    return out;
  }, [events]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 9e9, behavior: "smooth" });
  }, [turns, busy]);

  function submit() {
    const t = draft.trim();
    if (!t) return;
    send(t);
    setDraft("");
    requestAnimationFrame(() => taRef.current?.focus());
  }

  return (
    <section className="chat">
      <div className="stream" ref={scrollRef}>
        {turns.length === 0 && (
          <div className="msg assistant">
            <strong>Hi. I'm Scawward.</strong>
            <p style={{ margin: "8px 0 0" }}>
              Tell me what to do — I can read files, launch apps, search the
              web, see your screen, and chain it all together.
            </p>
            <p style={{ margin: "8px 0 0", color: "var(--fg-dim)", fontSize: 13 }}>
              Try: <em>"What's on my screen right now?"</em>
            </p>
          </div>
        )}

        {turns.map((t, i) => {
          if (t.role === "user") {
            return (
              <div key={i} className="msg user">
                {t.text}
              </div>
            );
          }
          if (t.role === "assistant") {
            return (
              <div key={i} className="msg assistant markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {t.text}
                </ReactMarkdown>
              </div>
            );
          }
          if (t.role === "error") {
            return (
              <div key={i} className="msg error">
                ⚠ {t.text}
              </div>
            );
          }
          // tool
          const preview = toolResultPreview(t.result);
          return (
            <div key={i} className={`msg tool ${preview.ok ? "ok" : "ko"}`}>
              <div className="tool-head">
                <span className="tool-name">{t.name}</span>
                <span className="tool-args">{compactInput(t.input)}</span>
              </div>
              <div className="tool-result">
                <span className={preview.ok ? "result-ok" : "result-ko"}>
                  {preview.ok ? "✓" : "✗"}
                </span>{" "}
                {preview.text}
              </div>
            </div>
          );
        })}

        {busy && (
          <div className="msg assistant thinking">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </div>
        )}
      </div>

      <div className="composer">
        <textarea
          ref={taRef}
          placeholder={connected ? "Ask Scawward to do anything…" : "Connecting…"}
          value={draft}
          disabled={!connected || busy}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button onClick={submit} disabled={!connected || busy || !draft.trim()}>
          {busy ? "…" : "Send"}
        </button>
      </div>
    </section>
  );
}
