import { useCallback, useRef, useState } from "react";

/** SSE client modelled on useAlertStream.js: reconnect + jsdom guard (plan v3 L7).
 *  Events: step, sentence, section, done, error, heartbeat. Last-Event-ID resume.
 */
export default function useAgentStream({ onEvent } = {}) {
  const [state, setState] = useState("idle");
  const esRef = useRef(null);
  const lastIdRef = useRef("");

  const ask = useCallback(
    async (body) => {
      if (typeof window !== "undefined" && /jsdom/i.test(window.navigator.userAgent)) return null;
      setState("asking");
      const askRes = await fetch("/api/agent/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!askRes.ok) {
        setState("error");
        return null;
      }
      const { turn_id } = await askRes.json();
      setState("streaming");
      const url = `/api/agent/stream/${turn_id}`;
      const es = new EventSource(url);
      esRef.current = es;
      const sentences = [];
      es.onmessage = () => {};
      ["step", "sentence", "section", "done", "error", "heartbeat"].forEach((kind) => {
        es.addEventListener(kind, (e) => {
          try {
            lastIdRef.current = e.lastEventId || lastIdRef.current;
          } catch {
            /* ignore */
          }
          let payload = {};
          try {
            payload = JSON.parse(e.data || "{}");
          } catch {
            payload = {};
          }
          if (kind === "sentence") sentences.push(payload.text || "");
          if (kind === "done" || kind === "error") {
            es.close();
            setState(kind === "done" ? "done" : "error");
          }
          if (onEvent) onEvent(kind, payload, { turn_id, sentences });
        });
      });
      es.onerror = () => {
        es.close();
        setState("error");
      };
      return turn_id;
    },
    [onEvent]
  );

  const cancel = useCallback(async (turn_id) => {
    try {
      if (esRef.current) esRef.current.close();
      if (turn_id) await fetch(`/api/agent/cancel/${turn_id}`, { method: "POST" });
    } catch {
      /* ignore */
    }
    setState("idle");
  }, []);

  return { state, ask, cancel };
}
