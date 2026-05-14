import { useEffect, useState } from "react";

export interface Health {
  ok: boolean;
  version: string;
  tools: string[];
  has_api_key: boolean;
  llm_provider: string;
  llm_model: string;
  llm_ready: boolean;
  ollama_reachable: boolean;
  ollama_models: string[];
}

export function useHealth(): { health: Health | null; refresh: () => void } {
  const [health, setHealth] = useState<Health | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let attempt = 0;

    async function probe() {
      while (!cancelled) {
        try {
          const r = await fetch("/api/health");
          if (r.ok) {
            const j = (await r.json()) as Health;
            if (!cancelled) {
              setHealth(j);
              attempt = 0;
              await new Promise((res) => setTimeout(res, 15_000));
              continue;
            }
          }
        } catch {
          /* swallow */
        }
        attempt += 1;
        const delay = Math.min(400 * 2 ** Math.min(attempt, 5), 8000);
        await new Promise((res) => setTimeout(res, delay));
      }
    }

    probe();
    return () => {
      cancelled = true;
    };
  }, [tick]);

  return {
    health,
    refresh: () => setTick((t) => t + 1),
  };
}
