import { useEffect, useState } from "react";

export interface Health {
  ok: boolean;
  version: string;
  tools: string[];
  has_api_key: boolean;
}

export function useHealth(): Health | null {
  const [h, setH] = useState<Health | null>(null);

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
              setH(j);
              attempt = 0;
              // Once we have a value, recheck every 15s in the background
              // so the topbar stays accurate (api key revoked, tool added).
              await new Promise((res) => setTimeout(res, 15000));
              continue;
            }
          }
        } catch {
          /* swallow — fall through to backoff */
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
  }, []);

  return h;
}
